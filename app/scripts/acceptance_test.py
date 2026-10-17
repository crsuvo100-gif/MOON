# Wrapper acceptance test script for CI when repository is copied from parent directory.
# It forwards to the real script located in the MOON package.
import subprocess, sys, pathlib

def main():
    # Resolve the actual script location relative to this wrapper.
    repo_root = pathlib.Path(__file__).resolve().parents[2]  # app/scripts -> repo root
    real_script = repo_root / "scripts" / "acceptance_test.py"
    if not real_script.is_file():
        print(f"Missing real acceptance_test.py at {real_script}")
        sys.exit(2)
    # Execute the real script using the same interpreter.
    result = subprocess.run([sys.executable, str(real_script)], capture_output=True, text=True)
    print(result.stdout)
    sys.stderr.write(result.stderr)
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()
