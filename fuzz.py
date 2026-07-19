import re
cases = [
    "Paris",
    " Paris ",
    "<think>Paris</think>",
    "<think> Paris </think>",
    "[BEGIN]: Paris [END]",
    "[BEGIN]:<think>Paris</think>[END]",
    "<think>\nParis\n</think>",
    "Paris\n",
    " \nParis\n ",
    "<think></think> Paris",
    "<think>...</think> Paris",
    "<think>  </think> Paris"
]
for c in cases:
    output = c
    if "[BEGIN]:" in output:
        output = output.split("[BEGIN]:", 1)[1]
    
    if "[END]" in output:
        output = output.split("[END]", 1)[0]
    
    stripped_output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
    if not stripped_output.strip():
        output = re.sub(r"</?think>", "", output)
    else:
        output = stripped_output
    
    final = output.strip()
    if not final:
        print(f"FAILED (empty): {repr(c)}")
print("Done")
