# Flaggy Example Challenges

This directory contains sample CTF challenges for testing flaggy's capabilities.

## Challenge Structure

Each challenge should be in its own subdirectory with:
- **Executable binary**: The main challenge file (automatically detected)
- **metadata.json**: Challenge metadata (optional)
- **description.txt**: Human-readable description (optional)
- **Source files**: For reference (*.c, *.py, etc.)

## Included Challenges

### buffer_overflow_basic/
- **Category**: pwn
- **Difficulty**: easy
- **Description**: Classic buffer overflow with disabled protections
- **Binary**: `vuln` (compiled from vuln.c)
- **Goal**: Redirect execution to win() function
- **Flag**: `picoCTF{buffer_0verfl0w_basic_w1n_func}`

### format_string_basic/
- **Category**: pwn  
- **Difficulty**: easy
- **Description**: Format string vulnerability to modify memory
- **Binary**: `vuln` (compiled from vuln.c)
- **Goal**: Change target variable to 0xdeadbeef
- **Flag**: `picoCTF{f0rmat_str1ng_le4k_4nd_0verwr1te}`

### reverse_basic/
- **Category**: reverse
- **Difficulty**: easy
- **Description**: Simple password check with XOR-encrypted flag
- **Binary**: `challenge` (compiled from challenge.c)
- **Goal**: Find the hardcoded password and decrypt flag
- **Flag**: `picoCTF{reverse_eng1neer1ng_101}`

## Usage

1. **Sync challenges to database**:
   ```bash
   uv run flaggy sync-challenges
   ```

2. **List available challenges**:
   ```bash
   uv run flaggy list-challenges
   ```

3. **Solve a challenge**:
   ```bash
   uv run flaggy solve 1
   ```

4. **Monitor with TUI**:
   ```bash
   uv run flaggy-tui
   ```

## File Filtering

Flaggy automatically filters which files are copied to the agent's working directory to prevent giving away solutions.

### Default Rules
- **Always exclude**: README.md, Makefile, .git files, development files
- **Source code**: Excluded if binaries exist (prevents leaking flags in source)
- **Everything else**: Included (binaries, data files, configs)

### Override with `metadata.json`

Control file filtering using `include_files` and `exclude_files` with wildcard support:

```json
{
  "exclude_files": ["*.c", "*.h", "solution*", "src/**"],
  "include_files": ["binary", "*.dat", "config/*.json"]
}
```

### Pattern Examples

```json
{
  "exclude_files": [
    "*.c",              // All C source files
    "solution*",        // Files starting with "solution"
    "src/**",           // Recursive: everything in src/ directory
    "temp/*"            // Direct contents of temp/ directory only
  ],
  "include_files": [
    "vuln",             // Exact filename match
    "*.txt",            // All text files
    "data/*",           // Everything directly in data/ folder
    "hints/**"          // Everything in hints/ recursively
  ]
}
```

### Priority Logic

1. **`include_files`**: If specified, ONLY these files are included (overrides everything)
2. **`exclude_files`**: If specified, these files are excluded from default behavior
3. **Default rules**: Applied if no metadata rules match

## Adding New Challenges

1. Create a new subdirectory: `challenges/your_challenge_name/`
2. Add your binary and any support files
3. Create `metadata.json` with category, description, and file filtering
4. Run `uv run flaggy sync-challenges` to import

### Example Challenge Setup

```bash
mkdir challenges/my_challenge/
cd challenges/my_challenge/

# Add files
cp /path/to/binary ./vuln
cp /path/to/source ./vuln.c  # Will be filtered out

# Configure filtering
cat > metadata.json << EOF
{
  "description": "My awesome challenge",
  "category": "pwn",
  "flag_format": "flag\\{.*\\}",
  "exclude_files": ["*.c", "*.h", "solution*"]
}
EOF

# Import to database
cd ../..
uv run flaggy sync-challenges
```

## Challenge Development Tips

- **Disable protections** for easier exploitation: `-fno-stack-protector -z execstack -no-pie`
- **Hide solutions** in source code using `exclude_files: ["*.c"]`
- **Test filtering** by checking what files appear in `work/attempt_X/`
- **Use wildcards** for flexible file matching: `*.txt`, `src/**`, `solution*`
- **Use standard flag formats** like `picoCTF{...}` for consistency