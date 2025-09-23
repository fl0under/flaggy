import os
import json
import time
from typing import List, Dict, Any, Optional, Callable

import dspy

from ctf_solver.core.runner import ChallengeRunner
from ctf_solver.agent.dspy_agent import CTFAgent
from ctf_solver.config import OPENROUTER_API_KEY, CTF_MODEL


ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class BatchOptimizer:
    """
    Loader/saver for optimized CTFAgent instruction artifacts.

    Maintains compatibility for components that expect to load an
    optimized agent via an artifact name (used by ChallengeRunner and CLI).
    """

    def __init__(self, artifacts_dir: str = ARTIFACTS_DIR):
        self.artifacts_dir = artifacts_dir

    def _artifact_path(self, name: str) -> str:
        return os.path.join(self.artifacts_dir, name)

    def load_optimized_agent(self, name: str) -> Optional[CTFAgent]:
        try:
            base = self._artifact_path(name)
            instruction_file = os.path.join(base, "instruction.json")
            if not os.path.exists(instruction_file):
                return None
            with open(instruction_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            instruction = (data.get("instruction", "") or "").strip()
            if not instruction:
                return None
            agent = CTFAgent(container=None)
            # Apply the instruction to the agent's CoT signature
            try:
                if hasattr(agent.cot, 'signature') and hasattr(agent.cot.signature, 'instructions'):
                    agent.cot.signature.instructions = instruction
                else:
                    raise AttributeError("signature.instructions not available")
            except Exception:
                # Fallback: rebuild signature with the known schema and new instruction
                try:
                    new_sig = dspy.Signature(
                        "history_text, info, last_output -> analysis, approach, tool_name, command, filename, content, max_bytes",
                        instruction,
                    )
                    agent.cot = dspy.ChainOfThought(signature=new_sig)
                except Exception:
                    return None
            return agent
        except Exception:
            return None

    @staticmethod
    def save_instruction(name: str, instruction: str, metadata: Dict[str, Any]) -> str:
        _ensure_dir(ARTIFACTS_DIR)
        base = os.path.join(ARTIFACTS_DIR, name)
        _ensure_dir(base)
        with open(os.path.join(base, "instruction.json"), "w", encoding="utf-8") as f:
            json.dump({"instruction": instruction, "metadata": metadata}, f, ensure_ascii=False, indent=2)
        return base

    # Optional helpers used by some CLI utilities
    def list_saved_agents(self) -> List[Dict[str, Any]]:
        agents: List[Dict[str, Any]] = []
        try:
            if not os.path.isdir(self.artifacts_dir):
                return []
            for entry in sorted(os.listdir(self.artifacts_dir)):
                path = os.path.join(self.artifacts_dir, entry)
                if not os.path.isdir(path):
                    continue
                instruction_path = os.path.join(path, "instruction.json")
                if os.path.exists(instruction_path):
                    agents.append({
                        "name": entry,
                        "format": "cot_instruction",
                        "demo_count": 0,
                        "has_optimization": True,
                        "path": instruction_path,
                    })
        except Exception:
            return []
        return agents

class _FlaggyGEPAFeedbackMetric:
    """
    Lightweight metric: reads the program's prediction and returns score + feedback.

    Matches DSPy tutorials where the program does the work and the metric
    just summarizes (no side effects, no extra LLM calls, no reconfiguration).
    """

    def __init__(self, max_examples: int = 4, progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None):
        self.max_examples = max_examples
        self._progress_cb = progress_cb

    # GEPA may call with (gold, pred, trace) or (gold, pred, trace, pred_name, pred_trace)
    def __call__(self, gold: Any, pred: Any = None, trace: Any = None, pred_name: Any = None, pred_trace: Any = None, *args, **kwargs):
        # Normalize batch to first N items to keep GEPA light (gold unused here)
        try:
            success = False
            feedback = ""
            if isinstance(pred, dict):
                success = bool(pred.get("success"))
                feedback = str(pred.get("feedback", ""))
            else:
                # object-like
                success = bool(getattr(pred, "success", False))
                feedback = str(getattr(pred, "feedback", ""))
        except Exception:
            success = False
            feedback = ""
        # Lightweight progress update per metric call
        try:
            if callable(self._progress_cb):
                self._progress_cb({"type": "metric", "success": success})
        except Exception:
            pass
        return dspy.Prediction(score=1.0 if success else 0.0, feedback=feedback)

    # Metric no longer includes DB helpers; the program provides feedback


class StudentProgram(dspy.Module):
    """Thin wrapper so DSPy can call program(challenge_id=...) without
    invoking the agent. We expose the CoT module as `cot` so GEPA can
    mutate its instruction text.
    """

    def __init__(self, db_conn, container_prefix: str, seed_instruction: Optional[str]):
        super().__init__()
        self.db_conn = db_conn
        self.container_prefix = container_prefix
        # Build a standalone CoT signature for GEPA to mutate (no CTFAgent yet)
        sig = dspy.Signature(
            "history_text, info, last_output -> analysis, approach, tool_name, command, filename, content, max_bytes",
            seed_instruction or "",
        )
        self.cot = dspy.ChainOfThought(signature=sig)

    def forward(self, challenge_id: int):
        # Ensure LM is configured in this thread (DSPy settings are thread-local)
        try:
            if not getattr(dspy.settings, 'lm', None):
                dspy.configure(
                    lm=dspy.LM(
                        model="openrouter/openai/gpt-5-mini",
                        api_key=OPENROUTER_API_KEY,
                        api_base="https://openrouter.ai/api/v1",
                        temperature=1.0,
                        max_tokens=20000,
                    )
                )
        except Exception:
            pass

        # Save current instruction to a temporary artifact for ChallengeRunner
        try:
            instruction = getattr(self.cot.signature, 'instructions', '') or ''
        except Exception:
            instruction = ''

        _ensure_dir(ARTIFACTS_DIR)
        tmp_name = f"tmp_gepa_{int(time.time())}"
        tmp_dir = os.path.join(ARTIFACTS_DIR, tmp_name)
        _ensure_dir(tmp_dir)
        try:
            with open(os.path.join(tmp_dir, "instruction.json"), "w", encoding="utf-8") as f:
                json.dump({"instruction": instruction, "metadata": {"type": "gepa_eval"}}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # Run attempt
        container_base = f"{self.container_prefix}_{tmp_name}"
        runner = ChallengeRunner(self.db_conn, container_base, use_presenter=False, optimized_agent_name=tmp_name)
        flag = runner.run_attempt(challenge_id)

        # Build concise feedback from the attempt and short history
        snippet = self._collect_attempt_feedback(container_base)
        past = self._collect_past_runs_summary(challenge_id)
        feedback_parts = []
        if snippet:
            feedback_parts.append(f"Attempt summary for {challenge_id}:\n{snippet}")
        if past:
            feedback_parts.append(f"Past runs for {challenge_id}:\n{past}")
        feedback_text = "\n\n".join(feedback_parts)

        # Cleanup temp artifact
        try:
            import shutil
            shutil.rmtree(tmp_dir)
        except Exception:
            pass

        return {"success": bool(flag), "feedback": feedback_text}

    def _collect_attempt_feedback(self, container_base: str) -> str:
        try:
            cursor = self.db_conn.cursor()
            like_pattern = container_base + "%"
            cursor.execute(
                """
                SELECT id FROM attempts
                WHERE container_name LIKE %s
                ORDER BY started_at DESC, id DESC
                LIMIT 1
                """,
                (like_pattern,),
            )
            row = cursor.fetchone()
            if not row:
                return ""
            attempt_id = row[0]
            cursor.execute(
                """
                SELECT step_num, action, output, exit_code
                FROM steps
                WHERE attempt_id = %s
                ORDER BY step_num DESC
                LIMIT 4
                """,
                (attempt_id,),
            )
            steps = cursor.fetchall() or []
            lines: List[str] = []
            for step_num, action_json, output_bytes, exit_code in steps:
                try:
                    action = json.loads(action_json) if action_json else {}
                except Exception:
                    action = {}
                analysis = (action or {}).get("analysis", "")
                approach = (action or {}).get("approach", "")
                cmd = (action or {}).get("cmd", "")
                if isinstance(output_bytes, (bytes, bytearray)):
                    out_text = output_bytes.decode("utf-8", errors="replace")
                else:
                    out_text = str(output_bytes or "")
                out_text = (out_text or "").strip()
                if len(out_text) > 200:
                    out_text = out_text[:200] + "..."
                lines.append(
                    "\n".join(
                        filter(
                            None,
                            [
                                f"Step {step_num}",
                                f"Analysis: {analysis}" if analysis else None,
                                f"Approach: {approach}" if approach else None,
                                f"Command: {cmd}" if cmd else None,
                                (f"Exit: {exit_code}" if exit_code and exit_code != 0 else None),
                                f"Output: {out_text}" if out_text else None,
                            ],
                        )
                    )
                )
            return "\n\n".join(reversed(lines))
        except Exception:
            return ""

    def _collect_past_runs_summary(self, challenge_id: int, attempts_limit: int = 2, steps_limit: int = 3) -> str:
        try:
            cursor = self.db_conn.cursor()
            cursor.execute(
                """
                SELECT id FROM attempts
                WHERE challenge_id = %s AND status = 'completed'
                ORDER BY completed_at DESC, id DESC
                LIMIT %s
                """,
                (challenge_id, attempts_limit),
            )
            attempt_rows = cursor.fetchall() or []
            if not attempt_rows:
                return ""
            parts: List[str] = []
            for (attempt_id,) in attempt_rows:
                cursor.execute(
                    """
                    SELECT step_num, action, output, exit_code
                    FROM steps
                    WHERE attempt_id = %s
                    ORDER BY step_num DESC
                    LIMIT %s
                    """,
                    (attempt_id, steps_limit),
                )
                step_rows = cursor.fetchall() or []
                lines: List[str] = []
                for step_num, action_json, output_bytes, exit_code in step_rows:
                    try:
                        action = json.loads(action_json) if action_json else {}
                    except Exception:
                        action = {}
                    analysis = (action or {}).get("analysis", "")
                    approach = (action or {}).get("approach", "")
                    cmd = (action or {}).get("cmd", "")
                    if isinstance(output_bytes, (bytes, bytearray)):
                        out_text = output_bytes.decode("utf-8", errors="replace")
                    else:
                        out_text = str(output_bytes or "")
                    out_text = (out_text or "").strip()
                    if len(out_text) > 160:
                        out_text = out_text[:160] + "..."
                    lines.append(
                        " | ".join(
                            [
                                f"step {step_num}",
                                f"cmd: {cmd}" if cmd else "",
                                f"analysis: {analysis}" if analysis else "",
                                f"output: {out_text}" if out_text else "",
                            ]
                        ).strip(" | ")
                    )
                if lines:
                    parts.append("\n".join(reversed(lines)))
            return "\n\n".join(parts)
        except Exception:
            return ""


class DSPyGEPAOptimizer:
    """
    Optimizer that uses dspy.GEPA to evolve the CTFAgent's ChainOfThought instruction.

    Usage:
        optimizer = DSPyGEPAOptimizer(db_conn)
        result = optimizer.run(train_ids=[1,2,3], dev_ids=[4])

    The best instruction is saved under ctf_solver/optimization/artifacts/<name>/instruction.json
    and can be used via --optimized <name>.
    """

    def __init__(self, db_conn, container_name_prefix: str = "gepa", artifacts_dir: str = ARTIFACTS_DIR):
        self.db_conn = db_conn
        self.container_name_prefix = container_name_prefix
        self.artifacts_dir = artifacts_dir
        _ensure_dir(self.artifacts_dir)

    def _build_program(self, seed_instruction: Optional[str]) -> StudentProgram:
        return StudentProgram(self.db_conn, self.container_name_prefix, seed_instruction)

    @staticmethod
    def _save_final(name: str, instruction: str, metadata: Dict[str, Any]) -> str:
        _ensure_dir(ARTIFACTS_DIR)
        base = os.path.join(ARTIFACTS_DIR, name)
        _ensure_dir(base)
        with open(os.path.join(base, "instruction.json"), "w", encoding="utf-8") as f:
            json.dump({"instruction": instruction, "metadata": metadata}, f, ensure_ascii=False, indent=2)
        return base

    def run(
        self,
        train_ids: List[int],
        dev_ids: Optional[List[int]] = None,
        name: Optional[str] = None,
        seed_instruction: Optional[str] = None,
        auto: Optional[str] = None,
        max_full_evals: Optional[int] = None,
        max_metric_calls: Optional[int] = None,
        random_seed: int = 0,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        log_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        # Configure the primary LM once (main thread) so CTFAgent has a loaded LM
        try:
            if not getattr(dspy.settings, 'lm', None):
                main_lm = dspy.LM(
                    model=f"openrouter/{CTF_MODEL}",
                    api_key=OPENROUTER_API_KEY,
                    api_base="https://openrouter.ai/api/v1",
                    temperature=1.0 if CTF_MODEL.lower().startswith("openai/gpt-5") else 0.7,
                    max_tokens=20000 if CTF_MODEL.lower().startswith("openai/gpt-5") else 8000,
                )
                dspy.configure(lm=main_lm)
        except Exception:
            pass

        # Build student program wrapper exposing CoT for GEPA mutation
        program = self._build_program(seed_instruction)

        # Build train/val sets as dspy.Example to satisfy DSPy's evaluation API
        def to_examples(ids: List[int]) -> List[dspy.Example]:
            return [dspy.Example(challenge_id=cid).with_inputs("challenge_id") for cid in (ids or [])]

        trainset = to_examples(train_ids)
        valset = to_examples(dev_ids) if dev_ids else trainset

        # Metric reads program outputs only (no side effects)
        metric = _FlaggyGEPAFeedbackMetric(progress_cb=progress_callback)

        # Provide a reflection LM required by DSPy GEPA (defaults to your OpenRouter model)
        # Uses a higher max_tokens and temperature suitable for reflection
        reflection_lm = dspy.LM(
            model=f"openrouter/{CTF_MODEL}",
            api_key=OPENROUTER_API_KEY,
            api_base="https://openrouter.ai/api/v1",
            temperature=1.0,
            max_tokens=20000,
        )

        # Reduce DSPy internal logging noise during optimization
        try:
            import logging as _logging
            _logging.getLogger('dspy').setLevel(_logging.WARNING)
            _logging.getLogger('dspy.evaluate').setLevel(_logging.WARNING)
            _logging.getLogger('dspy.teleprompt').setLevel(_logging.WARNING)
        except Exception:
            pass

        # Encourage sequential evaluation to avoid thread-bound DSPy settings issues
        os.environ.setdefault("DSPY_NUM_THREADS", "1")
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        try:
            gepa = dspy.GEPA(
                metric=metric,
                auto=auto,
                max_full_evals=max_full_evals,
                max_metric_calls=max_metric_calls,
                track_stats=True,
                reflection_lm=reflection_lm,
                seed=random_seed,
                log_dir=log_dir,
                evaluator_kwargs={"num_threads": 1},
            )
        except TypeError:
            # Fallback if GEPA does not accept evaluator_kwargs
            gepa = dspy.GEPA(
                metric=metric,
                auto=auto,
                max_full_evals=max_full_evals,
                max_metric_calls=max_metric_calls,
                track_stats=True,
                reflection_lm=reflection_lm,
                seed=random_seed,
                log_dir=log_dir,
            )

        # Compile to evolve the instruction on the train/val sets
        new_prog = gepa.compile(program, trainset=trainset, valset=valset)

        # Extract best instruction from resulting program
        try:
            best_instruction = new_prog.cot.signature.instructions
        except Exception:
            best_instruction = seed_instruction or ""

        final_name = name or f"dspy_gepa_{int(time.time())}"
        path = self._save_final(final_name, best_instruction, {"source": "dspy.GEPA"})

        # Optionally expose stats if available
        try:
            result_dict = getattr(new_prog, "detailed_results", None)
        except Exception:
            result_dict = None

        return {
            "artifact_name": final_name,
            "artifact_path": path,
            "best_instruction": best_instruction,
            "details": str(result_dict) if result_dict else None,
            "log_dir": getattr(gepa, "log_dir", getattr(gepa, "run_dir", log_dir)),
        }


