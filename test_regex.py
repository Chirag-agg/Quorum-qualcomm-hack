import re

def parse(output):
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
        output = re.sub(r"</?think>", "", stripped_output)
    
    final_answer = output.strip()
    return final_answer

print("1:", parse("Paris"))
print("2:", parse("[BEGIN]:Paris[END]"))
print("3:", parse("<think>Thinking...</think>Paris"))
print("4:", parse("<think>Paris</think>"))
