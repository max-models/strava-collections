import subprocess
import sys

def test_npm_args(args):
    print(f"Running with args: {args}")
    # We use 'echo' to simulate what npm would see if it were called this way
    # Actually, npm is what we are calling, so let's see what it does.
    # But I don't want to actually run npm dev.
    # Let's just use a simple python script that prints sys.argv
    subprocess.run([sys.executable, "-c", "import sys; print(sys.argv)"] + args)

test_npm_args(["run", "dev", "-- --host"])
test_npm_args(["run", "dev", "--", "--host"])
