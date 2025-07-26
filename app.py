"""
title: EXI.AI-Q V1 [EXIF + AI + Q]
author: stefanpietrusky
author_url: https://downchurch.studio/
version: 1.0
"""

import os
import subprocess
import json
import uuid
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, session, send_from_directory, Response
from PIL import Image, PngImagePlugin

app = Flask(__name__)
app.secret_key = 'geheim' 

evaluation_status = {}

IMAGE_FOLDER = Path("images")

images = []
def load_images():
    global images
    images = [f for f in os.listdir(IMAGE_FOLDER)
              if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
    images.sort()
load_images()

def extract_metadata(image_path):
    ext = image_path.suffix.lower()
    if ext == ".png":
        try:
            img = Image.open(image_path)
            info = img.info
            desc = info.get("Description") or info.get("description")
            if desc:
                app.logger.debug(f"Pillow description found: {desc!r}")
                return desc.strip()
        except Exception as e:
            app.logger.debug(f"Pillow reading failed: {e}")

    try:
        exiftool_path = Path(r"\exiftool.exe").resolve()
        print(f"DEBUG: ExifTool-Path: {exiftool_path}")
        print(f"DEBUG: Bild-Path: {image_path}")
        result = subprocess.run(
            [str(exiftool_path), "-j", str(image_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            app.logger.debug(f"ExifTool-Error: {result.stderr.strip()}")
            return ""
        data = json.loads(result.stdout)[0]
        app.logger.debug("DEBUG ExifTool fields: %s", list(data.keys()))

        description = (
            data.get("ImageDescription")
            or data.get("Description")
            or data.get("XMP:Description")
            or data.get("IPTC:Caption-Abstract")
            or data.get("PNG:Comment")
            or next((v for k, v in data.items() if k.startswith("Text:")), None)
            or ""
        )
        return description.strip()
    except Exception as e:
        app.logger.debug(f"extract_metadata-Exception: {e}")
        return ""

def generate_question(description, difficulty):
    prompt = (
        f"Create a concise, direct question about the content at the {difficulty} level, "
        f"based on the following image description: {description}. "
        "The question must be clearly different from previous questions. "
        "The output should contain only the question sentence – without any additional preambles or explanations. "
        "Please generate a new formulation if the question is identical to a previous one. "
        "The file name should not be part of the question! "
    )

    process = subprocess.Popen(
        ["ollama", "run", "llama3.1p2", prompt],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='ignore'
    )
    try:
        stdout, stderr = process.communicate(timeout=60)
        if process.returncode != 0:
            print(f"Error during question generation: {stderr.strip()}")
            return "Error during question generation."
        return stdout.strip()
    except subprocess.TimeoutExpired:
        process.kill()
        return "Timeout during question generation."

@app.route('/generate-new-question', methods=['GET'])
def generate_new_question():
    difficulty = request.args.get("difficulty", "medium")
    image_filename = session.get("current_image")
    if not image_filename:
        return jsonify({"error": "No current image found."}), 400

    image_path = IMAGE_FOLDER / image_filename
    description = extract_metadata(image_path)
    if not description:
        description = f"Image: {image_filename}"

    new_question = generate_question(description, difficulty)
    if new_question == session.get("current_question"):
        new_question = generate_question(description, difficulty)

    question_id = str(uuid.uuid4())
    session["current_question_id"] = question_id
    session["current_question"] = new_question

    return jsonify({"question": new_question, "question_id": question_id})

def evaluate_answer_llm(question, user_answer, image_description):
    prompt = f"""
    Rate the following answer to the question: '{question}'.
    Answer: '{user_answer}'
    Context for the question (image description): '{image_description}'.
    The evaluation is based on the following image description: '{image_description}'.

    You must assign points from 1 to 10 for each of these four categories, based **only** on the supplied answer:
    1. Accuracy of content – is the statement technically correct?
    2. Quality of argumentation – is the explanation logical and comprehensible?
    3. Contextual reference – does the answer explicitly refer to the context of the question?
    4. Originality – does the answer contain your own wording or ideas?

    Assign points for each category from 1 to 10 and return the rating in the following JSON format:
    {{
        "Accuracy of content": {{"points": <Points>, "justification": "<Justification>"}},
        "Quality of argumentation": {{"points": <Points>, "justification": "<Justification>"}},
        "Contextual reference": {{"points": <Points>, "justification": "<Justification>"}},
        "Originality": {{"points": <Points>, "justification": "<Justification>"}},
        "Total score": <Total points>
    }}

    Make sure that the total score is the sum of the four categories.
    No meta answers or explanations outside of this format.
    """
    process = subprocess.Popen(
        ["ollama", "run", "llama3.1p2", prompt],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='ignore'
    )
    try:
        stdout, stderr = process.communicate(timeout=60)
        if process.returncode != 0:
            print(f"Error in rating request: {stderr.strip()}")
            return None, "Error in rating request."
        return stdout.strip(), None
    except subprocess.TimeoutExpired:
        process.kill()
        return None, "Timeout during evaluation request."

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/styles.css')
def styles():
    return Response(CSS_CONTENT, mimetype='text/css')

@app.route('/script.js')
def script():
    return Response(JS_CONTENT, mimetype='application/javascript')

@app.route('/get-question', methods=['GET'])
def get_question():
    difficulty = request.args.get("difficulty", "medium")
    
    index = session.get("image_index", 0)
    
    index = (index + 1) % len(images)
    session["image_index"] = index
    
    image_filename = images[index]
    image_path = IMAGE_FOLDER / image_filename
    
    description = extract_metadata(image_path)
    if not description:
        description = f"Bild: {image_filename}"
    question = generate_question(description, difficulty)
    
    question_id = str(uuid.uuid4())
    session["current_question_id"] = question_id
    session["current_question"] = question
    session["current_image"] = image_filename
    session["current_description"] = description
    
    session.pop("last_evaluation", None) 
    
    return jsonify({
        "image_url": f"/images/{image_filename}",
        "question": question,
        "question_id": question_id
    })

@app.route('/evaluate-answer', methods=['POST'])
def evaluate_answer():
    question_id = request.json.get('question_id')
    question = request.json.get('question')
    answer = request.json.get('answer') 

    if evaluation_status.get(question_id, False):
        return jsonify({
            "evaluation": "This question has already been evaluated.",
            "status": "already evaluated"
        })

    evaluation_status[question_id] = True
    image_description = session.get("current_description", "")

    evaluation_raw, err = evaluate_answer_llm(question, answer, image_description)
    if err:
        return jsonify({
            "evaluation": err,
            "status": "Error"
        }), 500

    try:
        evaluation = json.loads(evaluation_raw)
        required_categories = [
            "Accuracy of content",
            "Quality of argumentation",
            "Contextual reference",
            "Originality",
            "Total score"
        ]
        if not all(k in evaluation for k in required_categories):
            raise ValueError("Not all required categories were evaluated.")

        max_points_per_category = 10
        categories = [k for k in evaluation.keys() if k != "Total score"]
        max_total = len(categories) * max_points_per_category
        total_calculated = sum(int(evaluation[k]["points"]) for k in categories)
        if total_calculated != int(evaluation["Total score"]):
            raise ValueError("The total score does not match the sum of the categories.")

        threshold = max_total * 0.5  
        total_score = int(evaluation["Total score"])
        status = "answered" if total_score >= threshold else "unanswered"

        if total_score >= threshold:
            fazit = "Well done! Your answer meets the requirements."
        elif total_score >= threshold / 2:
            fazit = "The answer is partially correct; there is still room for improvement."
        else:
            fazit = "The answer is insufficient."

        formatted_evaluation = "".join([
            f"<p><strong>{k}</strong> [{v['points']}/{max_points_per_category}]: {v['justification']}</p>"
            for k, v in evaluation.items() if k != "Total score"
        ]) + f"<p><strong>Total score</strong> [{total_score}/{max_total}]: {fazit}</p>"

        session["last_evaluation"] = formatted_evaluation

        return jsonify({
            "evaluation": formatted_evaluation,
            "status": status
        })

    except json.JSONDecodeError:
        return jsonify({
            "evaluation": "Error parsing the rating. Make sure that the model returns valid JSON.",
            "status": "Error"
        }), 500
    except ValueError as ve:
        return jsonify({
            "evaluation": f"Valuation error: {str(ve)}",
            "status": "Error"
        }), 500
    except Exception as e:
        return jsonify({
            "evaluation": f"Unknown error: {str(e)}",
            "status": "Error"
        }), 500

@app.route('/submit-answer', methods=['POST'])
def submit_answer():
    question_id = session.get("current_question_id")
    question = session.get("current_question")
    data = request.get_json()
    user_answer = data.get("answer", "")
    payload = {
        "question_id": question_id,
        "question": question,
        "answer": user_answer
    }
    return evaluate_answer()

@app.route('/images/<filename>')
def serve_image(filename):
    return send_from_directory(str(IMAGE_FOLDER), filename)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EXF.AI-Q-V1</title>
    <link rel="stylesheet" href="/styles.css">
</head>
<body>
    <div class="container">
        <h1>EXF.AI-Q-V1</h1>
        
        <div class="difficulty-buttons">
            <button class="difficulty-button" data-level="easy">Easy</button>
            <button class="difficulty-button selected" data-level="medium">Medium</button>
            <button class="difficulty-button" data-level="difficult">Difficult</button>
        </div>

        <button id="loadQuestion">Load next image & question</button>
        <button id="generateNewQuestion">New question for current image</button>
        
        <div id="spinner" class="spinner" style="display: none;"></div>
        <div id="content" class="result-container" style="display:none;">

            <img id="image" src="" alt="Bild"/>
            
            <h2 id="question-title" style="display:none;">Question</h2>
            <div id="question-container">
                <div class="question" id="question"></div>
            </div>
            <div id="answer-container">
                <h2>Antwort</h2>
                <textarea id="answer" rows="4" placeholder="Your answer..." style="resize: none;"></textarea><br>
                <button id="submitAnswer">Send reply</button>
            </div>

            <div id="feedback-spinner" style="display: none;">
                <div id="eval-spinner" class="spinner"></div>
            </div>

            <div id="feedback-container" style="display: none;">
                <h2>Feedback</h2>
                <div id="eval-spinner" class="spinner" style="display: none;"></div>
                <div class="evaluation" id="evaluation"></div>
            </div>
        </div>
    </div>
    <script src="/script.js"></script>
</body>
</html>
"""

CSS_CONTENT = """
body {
    font-family: Arial, sans-serif;
    font-size: 16px;
    background-color: #f4f4f4;
    margin: 0;
    padding: 20px;
}
.container {
    width: 90%;
    max-width: 800px;
    margin: auto;
    background: white;
    padding: 20px;
    border-radius: 8px;
    border: 3px solid #262626;
    box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
    text-align: center;
}
h1, h2 {
    color: #333;
    margin: 1em 0 0.5em 0;
    text-align: center;
}
.difficulty-buttons {
    margin-bottom: 10px;
}
.difficulty-button {
    padding: 10px 10px;
    margin: 5px;
    border: 3px solid #262626;
    background-color: #ffffff;
    color: #262626;
    border-radius: 5px;
    cursor: pointer;
    font-size: 1rem; 
    font-family: inherit;
}
.difficulty-button.selected {
    border: 3px solid #262626;
    background-color: #00B0F0;
    color: #262626;
}
button {
    padding: 10px 10px;
    background-color: #ffffff;
    border: 3px solid #262626;
    color: #262626;
    border-radius: 5px;
    cursor: pointer;
    margin-top: 15px;
    margin: 5px;
    font-size: 1rem; 
    font-family: inherit;
}
button:hover {
    background-color: #262626;
    border: 3px solid #262626;
    color: #ffffff;
}
.result-container {
    margin-top: 20px;
}
img {
    max-width: 100%;
    height: auto;
    border: 3px solid #262626;
    border-radius: 5px;
}
.spinner {
    border: 8px solid #262626;
    border-top: 8px solid  #00B0F0;
    border-radius: 50%;
    width: 50px;
    height: 50px;
    animation: spin 1s linear infinite;
    margin: 20px auto;
}
@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}
textarea {
    width: 100%;
    padding: 10px;
    margin-top: 10px;
    resize: none;
    box-sizing: border-box;
    border: 3px solid #262626;
    border-radius: 5px;
    font-family: Arial, sans-serif;
}
#question-container {
    margin: 15px 0;
    padding: 10px;
    border: 3px solid #262626;
    border-radius: 5px;
    background-color: #f9f9f9;
    text-align: left;
}
.evaluation {
    margin-top: 20px;
    border: 3px solid #262626;
    background-color: #00B0F0;
    color: #262626;
    padding: 15px;
    border-radius: 5px;
    text-align: left;
}
.evaluation p strong {
    font-weight: bold;
}
#submitAnswer {
  margin-top: 20px;
}
textarea:focus,
input:focus {
  outline: none;   
  border: 3px solid #00B0F0;
  box-shadow: 0 0 0 4px #96DCF8;
}
"""

JS_CONTENT = """
document.addEventListener('DOMContentLoaded', function() {
    const difficultyButtons = document.querySelectorAll('.difficulty-button');
    let selectedDifficulty = "medium";

    difficultyButtons.forEach(button => {
        button.addEventListener('click', function() {
            difficultyButtons.forEach(btn => btn.classList.remove('selected'));
            this.classList.add('selected');
            selectedDifficulty = this.getAttribute('data-level');
        });
    });

    const loadQuestionBtn = document.getElementById("loadQuestion");
    const generateNewQuestionBtn = document.getElementById("generateNewQuestion");
    const spinner = document.getElementById("spinner");
    const contentContainer = document.getElementById("content");
    const questionTitle = document.getElementById("question-title");
    const questionContainer = document.getElementById("question");
    const answerField = document.getElementById("answer");

    const feedbackSpinner = document.getElementById("feedback-spinner");
    const evalSpinner = document.getElementById("eval-spinner");
    const feedbackContainer = document.getElementById("feedback-container");
    const evaluationDiv = document.getElementById("evaluation");

    loadQuestionBtn.addEventListener("click", function(){
        feedbackSpinner.style.display = "none";
        evalSpinner.style.display = "none";
        feedbackContainer.style.display = "none";
        evaluationDiv.innerHTML = "";

        spinner.style.display = "block";
        contentContainer.style.display = "none";
        questionTitle.style.display = "none";
        answerField.value = "";

        fetch("/get-question?difficulty=" + selectedDifficulty)
            .then(response => response.json())
            .then(data => {
                spinner.style.display = "none";
                document.getElementById("image").src = data.image_url;
                questionContainer.innerText = data.question;
                contentContainer.style.display = "block";
                questionTitle.style.display = "block";
            })
            .catch(error => {
                spinner.style.display = "none";
                console.error("Error loading question:", error);
            });
    });

    generateNewQuestionBtn.addEventListener("click", function() {
        spinner.style.display = "block";

        fetch("/generate-new-question?difficulty=" + selectedDifficulty)
            .then(response => response.json())
            .then(data => {
                spinner.style.display = "none";
                if (data.error) {
                    alert(data.error);
                    return;
                }
                questionContainer.innerText = data.question;
            })
            .catch(error => {
                spinner.style.display = "none";
                console.error("Error generating the new question:", error);
            });
    });

    document.getElementById("submitAnswer").addEventListener("click", function(){
        const answer = answerField.value.trim();
        if (!answer) {
            alert("Please enter a response.");
            return;
        }

        feedbackSpinner.style.display = "block";
        evalSpinner.style.display = "block";
        feedbackContainer.style.display = "none";
        evaluationDiv.innerHTML = "";

        const payload = {
            question: questionContainer.innerText,
            answer: answer
        };

        fetch("/evaluate-answer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        })
        .then(response => response.json())
        .then(data => {
            feedbackSpinner.style.display = "none";
            evalSpinner.style.display = "none";
            feedbackContainer.style.display = "block";
            evaluationDiv.innerHTML = data.evaluation;
        })
        .catch(error => {
            feedbackSpinner.style.display = "none";
            evalSpinner.style.display = "none";
            console.error("Error sending response:", error);
        });
    });
});
"""
if __name__ == '__main__':
    app.run(debug=True)
