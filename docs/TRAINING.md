# Training cyber models without contaminating the eval

The golden rule: **train and eval share the same harness (operator image +
Terminus + `/logs`), but draw from disjoint task pools.** Cybench and NYU CTF are
held-out eval only — never train on them.

## Training pools (disjoint from eval)

- **`flaggy generate`** — procedural CTF tasks. Generated, not scraped, so zero
  overlap with any benchmark; self-grading on exact flag (clean RLVR reward);
  deterministic; ships solvable oracles. Start here — it needs no downloads and
  every task is provably solvable.
- **CTF-Dojo** — 658 executable CTF environments, already decontaminated against
  eval benchmarks. The closest drop-in external training corpus.
  (<https://arxiv.org/pdf/2508.18370>)
- **pwn.college CTF Archive** — runnable past-competition challenges.
  (<https://github.com/pwncollege/ctf-archive>)
- **InterCode-CTF** — ~100 picoCTF tasks; good easy-end curriculum.

All of these can be brought into the Harbor task format and `operatorize`d onto
the same operator image, exactly like the Cybench adapter.

## Two levers

1. **SFT / continued pretraining**
   - On security *text* (books, blogs, docs, man pages): cheap knowledge floor,
     but teaches narration, not interactive tool use.
   - On *trajectories* (stronger): synthesize from writeups à la **Cyber-Zero**
     (+13.1% across InterCode/NYU CTF/Cybench, runtime-free), and/or
     rejection-sample successful trajectories from your own/teacher rollouts on
     the training pool (expert iteration). The generator's oracle solutions are
     ready-made positive trajectories.
     (<https://arxiv.org/abs/2508.00910>, <https://github.com/amazon-science/Cyber-Zero>)

2. **RL with verifiable rewards (GRPO/PPO)**
   - Flag capture is a perfect verifiable reward. The central difficulty is
     **sparse reward** — most rollouts capture nothing. Mitigate with: a strong
     SFT warm-start, a difficulty curriculum, subtask/milestone shaping, and
     **hindsight relabeling** (Microsoft ECHO) to extract signal from failures.
     (<https://www.microsoft.com/en-us/research/publication/sample-efficient-online-learning-in-lm-agents-via-hindsight-trajectory-rewriting/>)
   - **Agent Lightning** bolts RL onto an existing agent loop without rewriting
     it — a natural fit for the Terminus/Harbor setup.
     (<https://www.microsoft.com/en-us/research/blog/agent-lightning-adding-reinforcement-learning-to-ai-agents-without-code-rewrites/>)

## Recommended order

```
1. SFT on decontaminated security text         -> knowledge floor
2. SFT on trajectories (Cyber-Zero / rejection-sampled oracles) -> tool-use loop
3. RLVR (GRPO) on the disjoint pool, reward = flag, ECHO for sparse reward
4. Held-out eval on Cybench + NYU CTF, with decontamination audits
```

For a solo effort on an open local model, stages 1–2 give most of the gain for
the least compute; treat RL as the cherry, not the main course.

## Decontamination (the silent failure mode)

Writeups for Cybench challenges are all over the internet — scrape them for SFT
and you can leak eval answers and "improve" by memorizing. Filter scraped data by
challenge name / competition / year (exclude Cybench's 2022–2024 source events),
prefer already-decontaminated corpora (CTF-Dojo), and run a periodic overlap
audit between training data and the eval sets. The procedural pool sidesteps this
entirely.
