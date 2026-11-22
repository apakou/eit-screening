"""Textes du formulaire « MEST AI Startup Program (Class of 2026) ».

Libellés, aides et introductions repris de l'export réel, pour que les
dossiers fictifs posent exactement les mêmes questions. Seules les réponses
sont inventées.
"""

PROGRAM = "MEST AI Startup Program (Class of 2026)"

TASK_ELIGIBILITY = "Program Eligibility Screening"
TASK_ASSESSMENT = "Complete your Assessment"
TASK_REFLECTION = "Upload your reflections on the assessment"
FORM_TITLE = "Application Form"

ELIGIBILITY_INTRO = [
    "To ensure the MEST AI Startup Program is the right fit for you, we ask that you complete "
    "this brief eligibility screening. Your responses will help us determine if you meet the "
    "core criteria for participation in the program. These questions cover key requirements "
    "such as age, citizenship, academic or entrepreneurial background, software development "
    "experience, commitment level, and your readiness to relocate and collaborate.",
    "Please answer honestly and thoroughly. Only candidates who meet the outlined criteria "
    "will be invited to continue with the full application.",
]

# (clé, question, aide éventuelle)
ELIGIBILITY_QUESTIONS: list[tuple[str, str, str | None]] = [
    ("citizen_of_region", "Are you a citizen of a country in West Africa?", None),
    ("age_in_range", "Are you between the ages of 21-30?", None),
    (
        "has_degree",
        "Do you hold a degree, diploma, or equivalent experience (i.e. work experience, "
        "certifications, training courses, etc.)?",
        None,
    ),
    (
        "software_experience",
        "Do you have experience in software development (can be entry/beginner level)?",
        None,
    ),
    (
        "ready_to_launch",
        "Do you feel ready and committed to launching your own business as an entrepreneur?",
        None,
    ),
    ("ai_business", "Do you aspire to launch an AI Software business?", None),
    (
        "willing_to_cofound",
        "Are you willing to collaborate and co-found a business with 2–3 other entrepreneurs "
        "from the program?",
        None,
    ),
    (
        "full_time_commitment",
        "Are you willing to pause or leave your current work/academic commitments to fully "
        "commit to the MEST AI Startup Program for up to 12 months of training and potential "
        "incubation (January to December 2026)?",
        None,
    ),
    (
        "can_relocate",
        "Are you able to relocate to Accra, Ghana for 7 months of in-person training (January "
        "– July 2026), followed by a potential 4-month incubation period (September – December "
        "2026)?",
        "This program is fully funded and covers travel, accommodation, health care, "
        "immigration expenses, selected meals, and a monthly stipend.",
    ),
    (
        "communal_housing",
        "Are you open to living in communal housing with roommates during the program duration "
        "(training + incubation)?",
        None,
    ),
]

APPLICATION_INTRO = (
    "We encourage you to use your own voice and original ideas when responding to the "
    "application questions. While we fully support and advocate for the thoughtful use of AI, "
    "your responses should reflect your personal experiences, motivations, and goals—so we can "
    "truly understand your fit and passion for the MEST AI Startup Program. Please note that "
    "generic AI-generated responses will be detected and may negatively impact your application."
)

SECTION_PERSONAL = ("Personal Information", "Please carefully fill out the fields below.")
SECTION_EDUCATION = (
    "2. Education",
    "Please describe your highest academic qualification (in progress/completed) using the "
    "fields below.",
)
SECTION_WORK = (
    "3. Work Experience",
    "Please list your most recent work experiences (max. 2); starting with the most recent "
    "of them.",
)
SECTION_STATEMENTS = ("3. Personal Statements", "Take some time here to carefully self-reflect.")
SECTION_ESSAYS = (
    "4. Free Form Questions",
    "Please provide a written response to each question, with answers limited to 100 words "
    "or less.",
)
SECTION_RESUME = ("4. Resume & Evidence", None)
SECTION_REFERENCES = (
    "5. Reference Check",
    "Please provide the details of two (2) references that we can contact. One must be a "
    "professional reference, such as a supervisor, co-worker, internship manager, etc. The "
    "other should be an academic reference such as a facilitator, instructor, professor, etc. "
    "We will contact your references before we extend you an offer to join the MEST AI Startup "
    "Program. Prior to any reference contact, we will inform you so you can also inform your "
    "references.",
)

HELP_INTERVIEW_CITY = (
    "You must be from a West African country and be able to attend in-person interviews in "
    "Ghana, Nigeria or Senegal."
)
HELP_GENDER = "As stated on your International Passport."
HELP_EMAIL = "email@example.com"
HELP_PHONE = "Please include the country code e.g. +2348131234569"
HELP_REFERENCE_PHONE = "Please include the country code e.g +2348131234569"
HELP_LINKEDIN = "Please input your public LinkedIn profile e.g. http://linkedin.com/in/johndoe"
HELP_MAJOR = (
    "If your major/field of study is not listed, scroll to the bottom and select ''Other'', "
    "then specify in the field provided below."
)
HELP_INSTITUTION = (
    "If your institution is not listed, scroll to the bottom and select ''Other'', then "
    "specify in the field provided below."
)
HELP_RELATIONSHIP = "Please describe your relationship with this person."
HELP_REFERENCE_NAME = {
    "professional": "Please provide the full name of your professional reference, i.e. "
    "supervisor, co-worker, internship manager, etc.",
    "academic": "Please provide the full name of your academic reference, i.e. facilitator, "
    "instructor, professor, etc.",
}

VIDEO_PROMPT = [
    "Please upload a video personal statement of 2 minutes or less that includes the following:",
    "1. Why you are applying to the MEST AI Startup Program.",
    "2. What moment or experience made you realize you want to become a tech entrepreneur.",
    "3. Please share about any software development experience or entrepreneurial experience "
    "you have.",
    "4. What you hope to gain from the MEST AI Startup Program that you believe you cannot get "
    "from any other program or experience.",
]

ESSAY_QUESTIONS = [
    "If you had unlimited time and resources to build any AI-software powered product, what "
    "would it be?",
    "Describe a time when you took an unconventional approach to solve a problem. What was "
    "the result?",
    "Tell us about a time you led a team through a difficult situation. How did you motivate "
    "others and what did you learn about leadership?",
    "What does success mean to you, and how do you measure it in your life?",
    "Tell us about a long-term goal you stuck with despite setbacks. What kept you going?",
]

RESUME_PROMPT = "Please upload your one-page resume (PDF)."
EVIDENCE_PROMPT = [
    "Please upload any supporting documents that verify your experience or expertise (no more "
    "than 3 of the most relevant).",
    "[i.e. certifications, completed courses, GitHub profiles, personal portfolio websites, "
    "live app/demo links, open-source contributions, etc.]",
]
EVIDENCE_URLS_PROMPT = [
    "If any of your supporting evidence is in the form of a link (e.g. personal portfolio, "
    "GitHub repositories, app/project demo, article, etc.), please provide the URL(s) below.",
    "You may submit a maximum of 5 evidence items in total—including uploaded files and any "
    "URLs. Please ensure your combined submissions do not exceed this limit.",
]

ASSESSMENT_TEXT = [
    "Please follow this link to access the MEST AI Startup Program Assessment on the "
    "TestGorilla platform. This test will take 70 minutes to complete. You will follow 3 steps:",
    '1. Register your email through the box on the right that says, "invite yourself to the '
    'assessment".',
    "2. Set up your device by checking audio and video.",
    "3. Take the assessment.",
    "Please visit the TestGorilla Step-by-Step Guide or the FAQ page if you are experiencing "
    "any challenges.",
    "You are required to complete all sections of the assessment. Once finished, return to "
    "your SurveyMonkey Apply application dashboard and submit a brief reflection on your "
    "assessment experience.",
    "Your application will only be considered complete once you have submitted the assessment "
    "and returned to the application to complete the reflection and submit the application.",
    "Please note:",
    "We take a holistic approach to reviewing applications. This means we consider all aspects "
    "of your submission, including your written responses, assessment results, and any "
    "accompanying materials to get a well-rounded view of your potential and fit for the "
    "program.",
    "The assessment is an important part of the process, and we encourage you to give it your "
    "best effort. However, please don’t feel overwhelmed. It’s not meant to be a barrier but "
    "rather a way for us to understand your current strengths and identify areas where you "
    "might grow and thrive within the program.",
    "Your application is more than just one component, and we’re looking forward to learning "
    "more about you through each part.",
]

REFLECTION_TEXT = [
    "Reflection is a key part of the entrepreneurial journey as it helps you grow, learn, and "
    "improve.",
    "Please upload a short video (1 minute max) sharing your experience with the recent test "
    "assessment.",
    "How you reflect is up to you, but if you need a starting point, consider these questions:",
    "How did you feel during and after the assessment?",
    "What went well?",
    "Where did you struggle?",
    "What did you find interesting or unexpected?",
    "Please ensure your submission does not exceed the 1-minute limit. Thank you for your "
    "cooperation.",
]
