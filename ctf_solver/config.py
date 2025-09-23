import os
import dspy
from pathlib import Path

# Load .env file if it exists
env_file = Path(__file__).parent.parent / '.env'
if env_file.exists():
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))

DB_DSN = os.environ.get('CTF_DSN', 'host=localhost port=5432 dbname=ctf user=flaggy password=flaggy123 sslmode=disable')

# OpenRouter configuration
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
if not OPENROUTER_API_KEY:
    print("Warning: OPENROUTER_API_KEY environment variable not set")
    print("Please set it in .env file or environment")

# Default model for CTF solving - can be changed via env var
CTF_MODEL = os.environ.get('CTF_MODEL', 'anthropic/claude-3.5-sonnet')

# Output size limits to prevent context window overflow
MAX_OUTPUT_TOKENS = int(os.environ.get('FLAGGY_MAX_OUTPUT_TOKENS', '50000'))
MAX_OUTPUT_CHARS = MAX_OUTPUT_TOKENS * 4  # Rough estimate: 1 token ≈ 4 chars

# ReAct/Runner controls
CTF_REACT_MAX_ITERS = int(os.environ.get('CTF_REACT_MAX_ITERS', '40'))
CTF_OUTER_MAX_STEPS = int(os.environ.get('CTF_OUTER_MAX_STEPS', '20'))
# Inner ReAct segment length per outer step (hybrid CoT+ReAct)
CTF_REACT_SEGMENT_ITERS = int(os.environ.get('CTF_REACT_SEGMENT_ITERS', '10'))

# Exegol tools categorized for CTF challenges
EXEGOL_TOOLS = {
    'binary_analysis': [
        'file', 'strings', 'objdump', 'readelf', 'nm', 'strip', 'hexdump', 'xxd',
        'checksec', 'rabin2', 'r2', 'radare2', 'ghidra', 'ida', 'binwalk', 'foremost',
        'volatility3', 'yara', 'pefile', 'upx', 'gdb'
    ],
    'debugging': [
        'gdb', 'pwndbg', 'peda', 'gef', 'ltrace', 'strace', 'valgrind',
        'rr', 'qemu-user', 'qemu-user-static'
    ],
    'exploitation': [
        'python3', 'python2', 'perl', 'ruby', 'php', 'nodejs', 'bash', 'sh', 'zsh',
        'ropper', 'ROPgadget', 'one_gadget', 'seccomp-tools', 'pwninit',
        'pwntools', 'angr', 'z3', 'sage', 'gmp-ecm'
    ],
    'network': [
        'nmap', 'masscan', 'nc', 'netcat', 'socat', 'curl', 'wget', 'httpx',
        'ffuf', 'gobuster', 'dirbuster', 'wfuzz', 'burpsuite', 'wireshark',
        'tcpdump', 'ngrep', 'ssh', 'telnet', 'ftp', 'smbclient'
    ],
    'web': [
        'sqlmap', 'nikto', 'dirb', 'wpscan', 'gobuster', 'ffuf', 'wfuzz',
        'burpsuite', 'zap', 'commix', 'xsser', 'jwt_tool'
    ],
    'crypto': [
        'openssl', 'gpg', 'john', 'hashcat', 'hash-identifier', 'hashid',
        'sage', 'gmpy2', 'pycryptodome', 'factordb-pycli', 'rsatool', 'featherduster'
    ],
    'forensics': [
        'volatility3', 'autopsy', 'sleuthkit', 'binwalk', 'foremost', 'scalpel',
        'photorec', 'testdisk', 'dd', 'dcfldd', 'ewf-tools', 'afflib-tools',
        'exiftool', 'steghide', 'outguess', 'stegsolve', 'zsteg'
    ],
    'reverse_engineering': [
        'ghidra', 'ida', 'radare2', 'r2', 'cutter', 'x64dbg', 'ollydbg',
        'upx', 'mz-tools', 'pe-tree', 'die', 'capa', 'yara', 'retdec'
    ],
    'mobile': [
        'adb', 'apktool', 'dex2jar', 'jadx', 'mobsf', 'frida', 'objection',
        'androguard', 'apkleaks', 'qark'
    ],
    'osint': [
        'theharvester', 'recon-ng', 'maltego', 'spiderfoot', 'shodan',
        'amass', 'subfinder', 'assetfinder', 'github-search'
    ],
    'post_exploitation': [
        'metasploit', 'empire', 'cobalt-strike', 'bloodhound', 'sharphound',
        'crackmapexec', 'impacket', 'responder', 'mimikatz', 'powershell'
    ],
    'utilities': [
        'tmux', 'screen', 'vim', 'nano', 'emacs', 'git', 'make', 'gcc', 'g++',
        'python3-pip', 'npm', 'go', 'rust', 'docker', 'kubectl', 'terraform'
    ]
}

# Critical tools that should always be available for CTF challenges
ESSENTIAL_CTF_TOOLS = [
    'file', 'strings', 'objdump', 'readelf', 'checksec-py', 'gdb', 'python3',
    'nc', 'curl', 'openssl', 'binwalk', 'radare2', 'ropper', 'one_gadget'
]

# Configure DSPy to use OpenRouter
def configure_dspy():
    """Configure DSPy with OpenRouter"""
    if not OPENROUTER_API_KEY:
        raise RuntimeError(
            "OPENROUTER_API_KEY environment variable is required but not set.\n"
            "Please add it to your .env file:\n"
            'OPENROUTER_API_KEY="your-api-key-here"'
        )
    
    # If already configured in this thread, do nothing
    try:
        if getattr(dspy.settings, 'lm', None):
            return getattr(dspy.settings, 'lm')
    except Exception:
        pass

    print(f"🤖 Configuring DSPy with model: {CTF_MODEL}")
    
    # Configure per-model parameters (OpenAI reasoning models need special settings)
    model_name = f"openrouter/{CTF_MODEL}"
    lower_model = CTF_MODEL.lower()
    is_openai_reasoning = (
        lower_model.startswith("openai/gpt-5")
        or lower_model.startswith("openai/o3")
        or lower_model.startswith("openai/o4")
    )

    temperature = 1.0 if is_openai_reasoning else 0.1
    max_tokens = 20000 if is_openai_reasoning else 20000

    openrouter_lm = dspy.LM(
        model=model_name,
        api_key=OPENROUTER_API_KEY,
        api_base="https://openrouter.ai/api/v1",
        # Enable conversation continuity and KV caching
        cache=False,
        temperature=temperature,
        max_tokens=max_tokens
    )
    try:
        dspy.configure(lm=openrouter_lm, adapter=dspy.ChatAdapter())
    except Exception:
        dspy.configure(lm=openrouter_lm)
    
    return openrouter_lm


def is_reasoning_model() -> bool:
    """Check if the current model is a reasoning model (o3, gpt-5, etc.)"""
    lower_model = CTF_MODEL.lower()
    return (
        lower_model.startswith("openai/gpt-5")
        or lower_model.startswith("openai/o3")
        or lower_model.startswith("openai/o4")
    )


