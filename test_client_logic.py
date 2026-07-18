import re

def process(output):
    if "[BEGIN]:" in output:
        output = output.split("[BEGIN]:", 1)[1]
    
    if "[END]" in output:
        output = output.split("[END]", 1)[0]
    
    # Strip any <think>...</think> blocks (even empty ones — they can appear doubled)
    stripped_output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
    if not stripped_output.strip():
        # If stripping think blocks leaves nothing, the answer was entirely inside them.
        # Remove just the tags instead.
        output = re.sub(r"</?think>", "", output)
    else:
        output = stripped_output
    
    final_answer = output.strip()
    return final_answer

print("1:", repr(process("Paris")))
print("2:", repr(process("[BEGIN]: Paris [END]")))
print("3:", repr(process("<think> Paris </think>")))
print("4:", repr(process("<think> thinking... </think> Paris")))
