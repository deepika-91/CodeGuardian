import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

# ============================================================
# CONFIGURATION
# ============================================================

BASE_MODEL = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
LORA_MODEL = "qwen_code_review_lora"

print("=" * 70)
print("HYBRID CODE REVIEW - LoRA INFERENCE")
print("=" * 70)

device = "cuda" if torch.cuda.is_available() else "cpu"
print("Device:", device)

# ============================================================
# LOAD TOKENIZER
# ============================================================

print("\nLoading tokenizer...")

tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# ============================================================
# LOAD BASE MODEL
# ============================================================

print("Loading base model...")

model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL,
    dtype=torch.float32
)

# ============================================================
# LOAD LoRA ADAPTER
# ============================================================

print("Loading LoRA adapter...")

model = PeftModel.from_pretrained(
    model,
    LORA_MODEL
)

model = model.to(device)
model.eval()

print("LoRA adapter loaded successfully.")

# ============================================================
# TEST CODE REVIEW
# ============================================================

code = """
public class UserService {

    private String password;

    public void setPassword(String password) {
        this.password = password;
    }

    public String getPassword() {
        return password;
    }
}
"""

patch = """
@@ -1,10 +1,14 @@
 public class UserService {

     private String password;

     public void setPassword(String password) {
         this.password = password;
     }

     public String getPassword() {
         return password;
     }
+
+    public void printPassword() {
+        System.out.println(password);
+    }
 }
"""

tool = "PMD"

# ============================================================
# PROMPT
# ============================================================

prompt = f"""You are an expert Java code reviewer.

Review the following code change.

Tool: {tool}

Code:
{code}

Patch:
{patch}

Identify the most important issue introduced by the patch.
Provide a concise code review comment explaining the problem and how to fix it.
"""

messages = [
    {
        "role": "system",
        "content": "You are an expert Java code reviewer."
    },
    {
        "role": "user",
        "content": prompt
    }
]

# ============================================================
# FORMAT CHAT
# ============================================================

text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True
)

inputs = tokenizer(
    text,
    return_tensors="pt",
    truncation=True,
    max_length=512
)

inputs = {
    key: value.to(device)
    for key, value in inputs.items()
}

# ============================================================
# GENERATE REVIEW
# ============================================================

print("\n" + "=" * 70)
print("GENERATING CODE REVIEW")
print("=" * 70)

with torch.no_grad():
    output = model.generate(
        **inputs,
        max_new_tokens=150,
        do_sample=False,
        temperature=1.0,
        pad_token_id=tokenizer.pad_token_id,
        eos_token_id=tokenizer.eos_token_id
    )

# Only decode generated portion
generated_tokens = output[0][inputs["input_ids"].shape[1]:]

review = tokenizer.decode(
    generated_tokens,
    skip_special_tokens=True
)

# ============================================================
# DISPLAY RESULT
# ============================================================

print("\nCODE REVIEW OUTPUT")
print("-" * 70)
print(review.strip())
print("-" * 70)

print("\nInference completed successfully")