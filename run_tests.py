import subprocess, sys, os

os.chdir(r"D:\WorkField\Projects\Ouroboros")
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests\\", "--tb=short", "-q"],
    capture_output=True, text=True, encoding="utf-8", errors="replace"
)
output = result.stdout + result.stderr
with open("test_results.txt", "w", encoding="utf-8") as f:
    f.write(output)
print("EXIT CODE:", result.returncode)
print(output[-3000:])
