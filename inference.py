import os
import re
import html
import subprocess
from pathlib import Path


import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel


# ============================================================
# CONFIGURATION
# ============================================================

# Base model used for LoRA training
BASE_MODEL = "Qwen/Qwen2.5-Coder-0.5B-Instruct"

# Your trained LoRA adapter
LORA_MODEL = "qwen_code_review_lora"

# Generated HTML file
HTML_FILE = "code_review.html"


# ============================================================
# DEVICE
# ============================================================

device = "cuda" if torch.cuda.is_available() else "cpu"

print("=" * 70)
print("HYBRID CODE REVIEW - LoRA INFERENCE")
print("=" * 70)
print(f"Device: {device}")
print()


# ============================================================
# LOAD TOKENIZER
# ============================================================

print("Loading tokenizer...")

tokenizer = AutoTokenizer.from_pretrained(
    BASE_MODEL,
    trust_remote_code=True
)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print("Tokenizer loaded successfully.")
print()


# ============================================================
# LOAD BASE MODEL
# ============================================================

print("Loading base model...")

if device == "cuda":

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )

else:

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.float32,
        trust_remote_code=True
    )

print("Base model loaded successfully.")
print()


# ============================================================
# LOAD LoRA ADAPTER
# ============================================================

print("Loading LoRA adapter...")

model = PeftModel.from_pretrained(
    model,
    LORA_MODEL
)

model.eval()

print("LoRA adapter loaded successfully.")
print()


# ============================================================
# JAVA CODE TO REVIEW
# ============================================================

code_to_review = """
public class TestExample {

    public static void main(String[] args) {
        int x = 10;
        int y = 20;

        if (x < y) {
            System.out.println("x is smaller");
        }

        System.out.println("Hello Hybrid Code Review");
    }
}
"""


# ============================================================
# STATIC ANALYZER OUTPUT
# ============================================================

static_analyzer_output = """
Checkstyle:
- Missing Javadoc comment for TestExample
- Missing Javadoc comment for main
- Indentation violations

PMD:
- SystemPrintln: Usage of System.out/err
- NoPackage: Class should belong to a named package
- ShortVariable: Avoid variables with short names like x
- ShortVariable: Avoid variables with short names like y
- LocalVariableCouldBeFinal: Local variable x could be final
- LocalVariableCouldBeFinal: Local variable y could be final
"""


# ============================================================
# CREATE PROMPT
# ============================================================

system_prompt = (
    "You are an expert in coding and code peer-reviewing."
)

user_prompt = f"""
### Code review comment generation

You will be assisted by outputs from static code analyzers
to generate a review comment given the code difference.

Given the code and static analyzer results below, generate a
clear code review that highlights potential issues and suggests
improvements.

### Static analyzer output

{static_analyzer_output}

### Code

{code_to_review}

### Instructions

Provide:

1. Issues found
2. Explanation of each issue
3. Suggested improvements
4. Improved code where appropriate
5. Time complexity
6. Space complexity

For complexity analysis, you MUST use exactly this format:

[TIME_COMPLEXITY]
O(...)

[SPACE_COMPLEXITY]
O(...)

Then provide the normal code review.

The complexity analysis must be based on the given code.

Consider:

- Loops
- Nested loops
- Recursion
- Data structures
- Number of operations
- Additional memory usage

Do not invent issues that are not supported by the code
or static analyzer results.
"""


# ============================================================
# CHAT TEMPLATE
# ============================================================

chat = [
    {
        "role": "system",
        "content": system_prompt
    },
    {
        "role": "user",
        "content": user_prompt
    }
]

prompt = tokenizer.apply_chat_template(
    chat,
    tokenize=False,
    add_generation_prompt=True
)


# ============================================================
# GENERATING CODE REVIEW
# ============================================================

print("=" * 70)
print("GENERATING CODE REVIEW")
print("=" * 70)
print()


inputs = tokenizer(
    prompt,
    return_tensors="pt",
    truncation=True,
    max_length=2048
)


# Move input tensors to model device
if device == "cuda":

    inputs = {
        key: value.to(model.device)
        for key, value in inputs.items()
    }

else:

    inputs = {
        key: value.to("cpu")
        for key, value in inputs.items()
    }


# ============================================================
# MODEL GENERATION
# ============================================================

with torch.no_grad():

    outputs = model.generate(
        **inputs,
        max_new_tokens=512,
        do_sample=True,
        temperature=0.2,
        top_p=0.9,
        repetition_penalty=1.05,
        pad_token_id=tokenizer.eos_token_id
    )


# ============================================================
# DECODE MODEL OUTPUT
# ============================================================

generated_tokens = outputs[0][
    inputs["input_ids"].shape[1]:
]

review = tokenizer.decode(
    generated_tokens,
    skip_special_tokens=True
).strip()


# ============================================================
# REMOVE UNWANTED ASSISTANT LABEL
# ============================================================

review = re.sub(
    r"^(assistant|Assistant)\s*:?\s*",
    "",
    review
).strip()


if not review:

    review = "No code review was generated."


# ============================================================
# EXTRACT TIME COMPLEXITY
# ============================================================

time_match = re.search(
    r"\[TIME_COMPLEXITY\]\s*(.*?)(?=\[SPACE_COMPLEXITY\]|$)",
    review,
    re.IGNORECASE | re.DOTALL
)


if time_match:

    time_complexity = time_match.group(1).strip()

else:

    time_complexity = "Not determined"


# ============================================================
# EXTRACT SPACE COMPLEXITY
# ============================================================

space_match = re.search(
    r"\[SPACE_COMPLEXITY\]\s*(.*?)(?=$)",
    review,
    re.IGNORECASE | re.DOTALL
)


if space_match:

    space_complexity = space_match.group(1).strip()

else:

    space_complexity = "Not determined"


# ============================================================
# CLEAN COMPLEXITY MARKERS FROM REVIEW
# ============================================================

review = re.sub(
    r"\[TIME_COMPLEXITY\].*?(?=\[SPACE_COMPLEXITY\])",
    "",
    review,
    flags=re.IGNORECASE | re.DOTALL
)


review = re.sub(
    r"\[SPACE_COMPLEXITY\].*?$",
    "",
    review,
    flags=re.IGNORECASE | re.DOTALL
)


review = review.strip()


# ============================================================
# CLEAN EXTRACTED COMPLEXITY
# ============================================================

time_complexity = time_complexity.split("\n")[0].strip()

space_complexity = space_complexity.split("\n")[0].strip()


if not time_complexity:

    time_complexity = "Not determined"


if not space_complexity:

    space_complexity = "Not determined"


# ============================================================
# AUTOMATIC JAVADOC GENERATION
# ============================================================

def generate_javadocs(java_code):
    """
    Automatically adds JavaDoc comments to Java classes and
    public/protected/private methods that do not already have
    a JavaDoc comment.
    """

    lines = java_code.splitlines()
    output = []

    class_pattern = re.compile(
        r'^(\s*)(?:(public|protected|private)\s+)?'
        r'(?:(abstract|final)\s+)?class\s+([A-Za-z_]\w*)'
    )

    method_pattern = re.compile(
        r'^(\s*)'
        r'(?:(public|protected|private)\s+)'
        r'(?:(static)\s+)?'
        r'(?:(final)\s+)?'
        r'(?:(<[^>]+>)\s+)?'
        r'([\w<>\[\], ?]+)\s+'
        r'([A-Za-z_]\w*)\s*'
        r'\(([^)]*)\)\s*'
        r'(?:throws\s+[^{]+)?\{'
    )

    for line in lines:
        stripped = line.strip()

        # Do not duplicate JavaDoc if the previous output line
        # already ends a JavaDoc block.
        previous_has_javadoc = bool(
            output and output[-1].strip().endswith("*/")
        )

        class_match = class_pattern.match(line)

        if class_match and not previous_has_javadoc:
            indent = class_match.group(1)
            class_name = class_match.group(4)

            output.extend([
                f"{indent}/**",
                f"{indent} * Represents the {class_name} class.",
                f"{indent} */"
            ])

        method_match = method_pattern.match(line)

        if method_match and not previous_has_javadoc:
            indent = method_match.group(1)
            return_type = method_match.group(6).strip()
            method_name = method_match.group(7)
            params = method_match.group(8).strip()

            output.append(f"{indent}/**")

            if method_name == "main":
                output.append(
                    f"{indent} * Entry point of the application."
                )
            else:
                output.append(
                    f"{indent} * Performs the {method_name} operation."
                )

            parameter_names = []

            if params:
                for parameter in params.split(","):
                    parameter = parameter.strip()

                    # Remove annotations such as @Nullable.
                    parameter = re.sub(
                        r'@\w+(?:\([^)]*\))?\s*',
                        '',
                        parameter
                    ).strip()

                    # Remove varargs marker from type only for parsing.
                    parts = parameter.split()

                    if len(parts) >= 2:
                        parameter_name = parts[-1]
                        parameter_names.append(parameter_name)

                        output.append(
                            f"{indent} *"
                        )
                        output.append(
                            f"{indent} * @param {parameter_name} "
                            f"parameter used by the method."
                        )

            if return_type != "void" and method_name != "main":
                output.append(
                    f"{indent} *"
                )
                output.append(
                    f"{indent} * @return result produced by the method."
                )

            output.append(f"{indent} */")

        output.append(line)

    return "\n".join(output)


generated_javadoc_code = generate_javadocs(code_to_review)

safe_javadoc = html.escape(generated_javadoc_code)


# ============================================================
# PREPARE HTML CONTENT
# ============================================================

safe_review = html.escape(review)

safe_code = html.escape(code_to_review)

safe_static = html.escape(
    static_analyzer_output
)

safe_time = html.escape(
    time_complexity
)

safe_space = html.escape(
    space_complexity
)


# ============================================================
# HTML PAGE
# ============================================================

html_content = f"""<!DOCTYPE html>

<html lang="en">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>Hybrid Code Review</title>


<style>

/* =========================================================
   GLOBAL
   ========================================================= */

* {{
    box-sizing: border-box;
}}


body {{

    margin: 0;

    padding: 0;

    font-family:
        Arial,
        Helvetica,
        sans-serif;

    background: #f4f6f8;

    color: #1f2937;
}}


/* =========================================================
   HEADER
   ========================================================= */

.header {{

    background: #111827;

    color: white;

    padding: 25px 40px;

    text-align: center;
}}


.header h1 {{

    margin: 0;

    font-size: 30px;
}}


.header p {{

    margin-top: 8px;

    color: #d1d5db;
}}


/* =========================================================
   MAIN CONTAINER
   ========================================================= */

.container {{

    width: 90%;

    max-width: 1200px;

    margin: 30px auto;
}}


/* =========================================================
   CARD
   ========================================================= */

.card {{

    background: white;

    border-radius: 12px;

    padding: 25px;

    margin-bottom: 25px;

    box-shadow:
        0 4px 15px rgba(0,0,0,0.08);
}}


.card h2 {{

    margin-top: 0;

    color: #111827;

    border-bottom:
        2px solid #e5e7eb;

    padding-bottom: 10px;
}}


/* =========================================================
   SOURCE CODE
   ========================================================= */

.code {{

    background: #111827;

    color: #e5e7eb;

    padding: 20px;

    border-radius: 8px;

    overflow-x: auto;

    white-space: pre-wrap;

    font-family:
        Consolas,
        "Courier New",
        monospace;

    line-height: 1.6;
}}


/* =========================================================
   AUTOMATIC JAVADOC
   ========================================================= */

.javadoc {{
    background: #111827;
    color: #e5e7eb;
    padding: 20px;
    border-radius: 8px;
    overflow-x: auto;
    white-space: pre-wrap;
    font-family:
        Consolas,
        "Courier New",
        monospace;
    line-height: 1.6;
}}



/* =========================================================
   STATIC ANALYZER
   ========================================================= */

.analyzer {{

    background: #f9fafb;

    border-left:
        5px solid #6366f1;

    padding: 20px;

    white-space: pre-wrap;

    font-family:
        Consolas,
        "Courier New",
        monospace;

    line-height: 1.6;
}}


/* =========================================================
   COMPLEXITY CONTAINER
   ========================================================= */

.complexity-container {{

    display: flex;

    gap: 20px;

    flex-wrap: wrap;
}}


/* =========================================================
   COMPLEXITY BOX
   ========================================================= */

.complexity-box {{

    flex: 1;

    min-width: 250px;

    background: #f9fafb;

    border:
        1px solid #e5e7eb;

    border-radius: 10px;

    padding: 25px;

    text-align: center;
}}


/* =========================================================
   COMPLEXITY TITLE
   ========================================================= */

.complexity-title {{

    font-size: 17px;

    font-weight: bold;

    margin-bottom: 15px;

    color: #374151;
}}


/* =========================================================
   COMPLEXITY VALUE
   ========================================================= */

.complexity-value {{

    font-size: 26px;

    font-weight: bold;

    color: #16a34a;

    font-family:
        Consolas,
        "Courier New",
        monospace;
}}


/* =========================================================
   AI REVIEW
   ========================================================= */

.review {{

    background: #f0fdf4;

    border-left:
        5px solid #16a34a;

    padding: 25px;

    white-space: pre-wrap;

    line-height: 1.7;

    font-size: 16px;

    border-radius: 8px;
}}


/* =========================================================
   BADGE
   ========================================================= */

.badge {{

    display: inline-block;

    background: #16a34a;

    color: white;

    padding: 6px 12px;

    border-radius: 20px;

    font-size: 13px;

    margin-bottom: 15px;
}}


/* =========================================================
   FOOTER
   ========================================================= */

.footer {{

    text-align: center;

    padding: 25px;

    color: #6b7280;

    font-size: 14px;
}}


/* =========================================================
   RESPONSIVE
   ========================================================= */

@media (max-width: 700px) {{

    .container {{

        width: 95%;
    }}

    .complexity-container {{

        flex-direction: column;
    }}

}}

</style>

</head>


<body>


<!-- =====================================================
     HEADER
     ===================================================== -->

<div class="header">

    <h1>
        Hybrid Code Review
    </h1>

    <p>
        AI-Powered Code Review using LoRA and Static Analysis
    </p>

</div>


<!-- =====================================================
     MAIN CONTENT
     ===================================================== -->

<div class="container">


    <!-- =================================================
         SOURCE CODE
         ================================================= -->

    <div class="card">

        <h2>
            Source Code
        </h2>

        <pre class="code">{safe_code}</pre>

    </div>


    <!-- =================================================
         STATIC ANALYZER RESULTS
         ================================================= -->

    <div class="card">

        <h2>
            Static Analyzer Results
        </h2>

        <pre class="analyzer">{safe_static}</pre>

    </div>


    <!-- =================================================
         AUTOMATIC JAVADOC GENERATION
         ================================================= -->

    <div class="card">

        <h2>
            Automatic JavaDoc Generation
        </h2>

        <pre class="javadoc">{safe_javadoc}</pre>

    </div>



    <!-- =================================================
         COMPLEXITY ANALYSIS
         ================================================= -->

    <div class="card">

        <h2>
            Complexity Analysis
        </h2>


        <div class="complexity-container">


            <!-- TIME COMPLEXITY -->

            <div class="complexity-box">

                <div class="complexity-title">

                    Time Complexity

                </div>


                <div class="complexity-value">

                    {safe_time}

                </div>

            </div>


            <!-- SPACE COMPLEXITY -->

            <div class="complexity-box">

                <div class="complexity-title">

                    Space Complexity

                </div>


                <div class="complexity-value">

                    {safe_space}

                </div>

            </div>


        </div>

    </div>


    <!-- =================================================
         AI GENERATED REVIEW
         ================================================= -->

    <div class="card">

        <h2>
            AI Generated Code Review
        </h2>


        <span class="badge">

            LoRA Model Generated

        </span>


        <div class="review">

            {safe_review}

        </div>

    </div>


</div>


<!-- =====================================================
     FOOTER
     ===================================================== -->

<div class="footer">

    Hybrid Code Review Project

    <br>

    Static Analysis + LoRA Fine-Tuned LLM

</div>


</body>

</html>
"""


# ============================================================
# SAVE HTML FILE
# ============================================================

html_path = Path(
    HTML_FILE
).resolve()


with open(
    html_path,
    "w",
    encoding="utf-8"
) as file:

    file.write(
        html_content
    )


# ============================================================
# TERMINAL OUTPUT
# ============================================================

print()

print("=" * 70)

print("CODE REVIEW GENERATED")

print("=" * 70)

print()

print("Time Complexity:")
print(time_complexity)

print()

print("Space Complexity:")
print(space_complexity)

print()

print("HTML file created:")

print(html_path)

print()

print("Opening review in Microsoft Edge...")


# ============================================================
# OPEN HTML IN MICROSOFT EDGE
# ============================================================

edge_paths = [

    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",

    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

]


edge_exe = None


for path in edge_paths:

    if os.path.exists(path):

        edge_exe = path

        break


if edge_exe:

    subprocess.Popen([
        edge_exe,
        str(html_path)
    ])

    print(
        "Microsoft Edge opened successfully."
    )

else:

    print()

    print(
        "Microsoft Edge executable was not found."
    )

    print(
        "You can open the HTML file manually:"
    )

    print(
        html_path
    )


print()

print(
    "Inference completed successfully."
)