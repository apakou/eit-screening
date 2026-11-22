"""Banque de textes des dossiers fictifs.

Tout ce qui suit est inventé. Les réponses existent en quatre registres, pour
que les dossiers couvrent des niveaux de qualité différents :

- ``fort``     : réponses précises, datées, chiffrées ;
- ``moyen``    : réponses sincères mais vagues ;
- ``faible``   : réponses très courtes ou hors sujet ;
- ``generique``: réponses lisses, sans aucun fait, typiques d'un texte
  produit par une IA sans relecture.

Les textes sont en anglais, comme le formulaire de MEST. Les marqueurs entre
accolades ({city}, {year}…) sont remplacés par les données du profil.
"""

# --------------------------------------------------------------------------
# Géographie
# --------------------------------------------------------------------------

# pays : (indicatif, ville principale, langue locale, établissements)
COUNTRIES: dict[str, tuple[str, str, str, list[str]]] = {
    "Ghana": ("+233", "Accra", "Twi", ["University of Ghana", "Kwame Nkrumah University of Science and Technology", "Ashesi University"]),
    "Nigeria": ("+234", "Lagos", "Yoruba", ["University of Lagos", "University of Ibadan", "Covenant University"]),
    "Senegal": ("+221", "Dakar", "Wolof", ["Université Cheikh Anta Diop", "École Supérieure Polytechnique de Dakar"]),
    "Côte d'Ivoire": ("+225", "Abidjan", "Dioula", ["Institut National Polytechnique Félix Houphouët-Boigny", "Université Félix Houphouët-Boigny"]),
    "Togo": ("+228", "Lomé", "Ewe", ["Université de Lomé"]),
    "Benin": ("+229", "Cotonou", "Fon", ["Université d'Abomey-Calavi"]),
    "Burkina Faso": ("+226", "Ouagadougou", "Mooré", ["Université Joseph Ki-Zerbo"]),
    "Mali": ("+223", "Bamako", "Bambara", ["Université des Sciences, des Techniques et des Technologies de Bamako"]),
    "Sierra Leone": ("+232", "Freetown", "Krio", ["Fourah Bay College"]),
    "The Gambia": ("+220", "Banjul", "Mandinka", ["University of The Gambia"]),
    "Liberia": ("+231", "Monrovia", "Kpelle", ["University of Liberia"]),
    "Guinea": ("+224", "Conakry", "Pular", ["Université Gamal Abdel Nasser de Conakry"]),
    "Niger": ("+227", "Niamey", "Hausa", ["Université Abdou Moumouni"]),
}
# Pondération : les trois pays d'entretien sont les plus représentés.
COUNTRY_WEIGHTS = {"Ghana": 9, "Nigeria": 9, "Senegal": 4, "Côte d'Ivoire": 3, "Togo": 3, "Benin": 2}

# Pays hors Afrique de l'Ouest et de l'Est (au sens de l'ONU comme de l'EAC),
# pour le scénario « nationalité hors zone ».
OUTSIDE_REGION = {"Cameroon": "+237", "South Africa": "+27", "Egypt": "+20", "Morocco": "+212"}

# Options du formulaire pour « country you are based in » et ville d'entretien associée.
BASED_IN_OPTIONS = {"Ghana": "Accra", "Nigeria": "Lagos", "Senegal": "Dakar"}
# Établissements supposés présents dans la liste déroulante du formulaire.
LISTED_INSTITUTIONS = {
    "University of Ghana",
    "Kwame Nkrumah University of Science and Technology",
    "Ashesi University",
    "University of Lagos",
    "University of Ibadan",
    "Covenant University",
}

# --------------------------------------------------------------------------
# Identités (combinaisons aléatoires : toute ressemblance serait fortuite)
# --------------------------------------------------------------------------

# Prénoms et noms regroupés par aire, pour que les combinaisons restent plausibles.
NAME_GROUPS = {
    "akan": {
        "Male": ["Kofi", "Kwame", "Yaw", "Kojo", "Ebo", "Kwesi"],
        "Female": ["Ama", "Abena", "Akosua", "Adjoa", "Efua", "Esi"],
        "last": ["Mensah", "Owusu", "Boateng", "Asante", "Appiah", "Adjei", "Agyeman", "Osei"],
    },
    "nigeria": {
        "Male": ["Chinedu", "Tunde", "Emeka", "Seun", "Femi", "Bashir"],
        "Female": ["Ngozi", "Amaka", "Funke", "Zainab", "Temi", "Hauwa"],
        "last": ["Okafor", "Adeyemi", "Balogun", "Eze", "Okonkwo", "Nwosu", "Bello", "Adebayo"],
    },
    "sahel": {
        "Male": ["Mamadou", "Ibrahima", "Moussa", "Cheikh", "Abdoulaye", "Ousmane", "Alpha", "Lamin"],
        "Female": ["Fatou", "Aminata", "Awa", "Mariam", "Aissatou", "Khady", "Binta", "Isatou"],
        "last": ["Diop", "Ndiaye", "Sow", "Fall", "Traore", "Diallo", "Bah", "Jallow", "Gueye", "Toure", "Sawadogo", "Zongo"],
    },
    "golfe": {
        "Male": ["Koffi", "Edem", "Kossi", "Yao", "Sena", "Komlan"],
        "Female": ["Afi", "Essi", "Akouvi", "Adjoua", "Sika", "Ablavi"],
        "last": ["Agbeko", "Lawson", "Amegah", "Soglo", "Houngbo", "Dossou", "Akakpo", "Kone", "Ouattara", "Kouassi"],
    },
    "mano": {
        "Male": ["Mohamed", "Sahr", "Abu", "Emmanuel"],
        "Female": ["Mariama", "Hawa", "Kadiatu", "Fatmata"],
        "last": ["Conteh", "Kamara", "Sesay", "Koroma", "Bangura", "Johnson"],
    },
    "hors_zone": {
        "Male": ["Thabo", "Junior", "Eric", "Samuel"],
        "Female": ["Lerato", "Grace", "Diane", "Sarah"],
        "last": ["Mbarga", "Nkosi", "Ndlovu", "Fouda", "Ebongue"],
    },
}
COUNTRY_NAME_GROUP = {
    "Ghana": "akan", "Nigeria": "nigeria",
    "Senegal": "sahel", "Mali": "sahel", "Guinea": "sahel", "The Gambia": "sahel",
    "Niger": "sahel", "Burkina Faso": "sahel",
    "Togo": "golfe", "Benin": "golfe", "Côte d'Ivoire": "golfe",
    "Sierra Leone": "mano", "Liberia": "mano",
}
EMAIL_DOMAINS = ["example.com", "example.org", "example.net"]

# --------------------------------------------------------------------------
# Parcours
# --------------------------------------------------------------------------

DEGREES = ["Bachelor's Degree", "Bachelor's Degree", "Master's Degree", "Higher National Diploma"]
MAJORS_TECH = [
    "Computer Science", "Software Engineering", "Information Technology",
    "Computer Engineering", "Electrical Engineering", "Mathematics", "Data Science",
]
MAJORS_OTHER = ["Economics", "Business Administration", "Marketing", "Accounting", "Agricultural Science"]

ORGANISATIONS = [
    "Sahel Digital", "Baobab Labs", "Kente Systems", "Harmattan Tech", "Lagune Software",
    "Volta Data", "Teranga Apps", "Atlantic Fintech", "Savane Analytics", "Akwaba Solutions",
    "Nimba Cloud", "Coastline Robotics", "Zongo Market Online", "Sunu Health",
]
JOB_TITLES = {
    "fort": [
        "Backend Developer", "Mobile Developer", "Machine Learning Intern", "Data Analyst",
        "Full Stack Developer", "Junior Software Engineer",
    ],
    "moyen": [
        "Junior Web Developer", "IT Support Officer", "Software Development Intern",
        "QA Tester", "Teaching Assistant", "Freelance Web Developer",
    ],
    "faible": ["Sales Assistant", "Data Entry Clerk", "Customer Service Agent", "Intern"],
}
SKILLS = {
    "fort": [
        "Python, FastAPI and PostgreSQL", "Flutter and Firebase", "React, Node.js and MongoDB",
        "Python, PyTorch and scikit-learn", "Java, Spring Boot and Android",
        "Django and React Native",
    ],
    "moyen": [
        "JavaScript and React", "PHP and MySQL", "Python and Django", "Flutter",
        "HTML, CSS and JavaScript", "Java",
    ],
    "faible": ["HTML and CSS", "a bit of Python", "Microsoft Office", "WordPress"],
}
TRAININGS = [
    "ALX Software Engineering Programme",
    "Google IT Support Professional Certificate",
    "freeCodeCamp Responsive Web Design",
    "AWS Certified Cloud Practitioner",
    "Andela Learning Community",
    "DataCamp Data Scientist with Python",
    "Meta Front-End Developer Certificate",
]
HEARD_ABOUT = ["Social media", "Friend or colleague", "MEST alumni", "University", "Online search", "Event"]

# --------------------------------------------------------------------------
# Question 1 : le produit rêvé
# --------------------------------------------------------------------------

IDEAS = [
    {
        "short": "a farming advice assistant that works with voice notes",
        "product": "a voice assistant that tells smallholder farmers, in their own language, when to plant, treat and sell",
        "pain": "My uncle grows maize near {city} and loses part of every harvest because advice arrives late or in English.",
        "step": "The first version would combine weather data, market prices and a speech model trained on {language} voice notes.",
        "measure": "I would measure it by the extra income a farmer keeps after one season.",
    },
    {
        "short": "a triage tool for community health workers",
        "product": "a triage assistant for community health workers that turns symptoms described by voice into a clear next step",
        "pain": "In the clinic where I volunteered in {city}, one nurse received more than eighty patients a day.",
        "step": "It would run offline on a cheap phone and flag the cases that must reach a doctor the same day.",
        "measure": "Success would be fewer late referrals for malaria and pregnancy complications.",
    },
    {
        "short": "a credit scoring tool for market traders",
        "product": "a credit score for market traders built from their mobile money history instead of payslips",
        "pain": "My mother has sold cloth in {city} for twenty years and still cannot get a bank loan.",
        "step": "The model would learn from repayment patterns that savings groups already record by hand.",
        "measure": "I would know it works when a trader gets a fair loan in a day instead of never.",
    },
    {
        "short": "an offline exam tutor for secondary school students",
        "product": "an AI tutor that prepares secondary school students for their final exams, even without internet",
        "pain": "At my former school in {city}, one maths teacher served four classes of sixty students.",
        "step": "It would explain past exam questions step by step and adapt to each student's mistakes.",
        "measure": "The measure would be the pass rate of schools that have no science teacher.",
    },
    {
        "short": "a delivery routing tool for cities without street addresses",
        "product": "a routing engine for motorbike couriers that learns real street conditions in cities without formal addresses",
        "pain": "When I delivered parcels in {city} during university, I lost hours finding houses described as near the blue kiosk.",
        "step": "It would turn landmarks and voice directions into precise locations and plan the route for the day.",
        "measure": "Success means a courier completes thirty percent more deliveries with the same fuel.",
    },
    {
        "short": "a plain-language contract assistant for small businesses",
        "product": "an assistant that explains contracts and tax notices to small business owners in plain language",
        "pain": "My first client in {city} signed a lease he did not understand and lost his shop deposit.",
        "step": "It would read a photographed document, highlight the risky clauses and suggest questions to ask.",
        "measure": "I would track how many disputes users avoid in their first year.",
    },
    {
        "short": "speech recognition for West African languages",
        "product": "speech recognition for {language} and other West African languages, good enough for call centres and clinics",
        "pain": "My grandmother cannot use any voice service because none of them understands her.",
        "step": "I would start by collecting and labelling voice data with local radio stations and universities.",
        "measure": "Success is an error rate low enough for a bank to answer its customers in {language}.",
    },
    {
        "short": "a flood warning service by SMS",
        "product": "a flood early-warning service that combines satellite images and river sensors and alerts households by SMS",
        "pain": "In {year}, floods in {city} destroyed the homes of my neighbours with only a few minutes of warning.",
        "step": "A first model would predict water levels six hours ahead for one river basin.",
        "measure": "The goal is simple: more families who leave in time.",
    },
    {
        "short": "a stock prediction tool for pharmacies",
        "product": "a demand forecasting tool that tells small pharmacies what to stock before they run out",
        "pain": "While working for a distributor in {city}, I saw pharmacies short of malaria drugs every rainy season.",
        "step": "It would learn from sales records, seasons and local outbreaks, and prepare the orders automatically.",
        "measure": "I would measure the number of days a pharmacy is out of essential medicines.",
    },
    {
        "short": "a job matching platform for artisans",
        "product": "a matching platform that turns the skills of informal artisans into verified profiles employers can trust",
        "pain": "My brother is an excellent electrician in {city} but finds jobs only by word of mouth.",
        "step": "AI would assess photos and short videos of finished work and collect customer feedback by voice.",
        "measure": "Success would be artisans earning a steady income from customers they have never met.",
    },
    {
        "short": "a demand forecasting tool for solar mini-grids",
        "product": "a forecasting system that helps solar mini-grid operators predict demand and prevent blackouts",
        "pain": "During my internship at a solar company near {city}, the grid failed every market day.",
        "step": "It would learn consumption patterns from smart meters and shift loads automatically.",
        "measure": "The measure is the number of hours of reliable electricity a village receives.",
    },
    {
        "short": "a tool that predicts minibus arrivals",
        "product": "a service that predicts when the next shared minibus will arrive and how full it will be",
        "pain": "Like most people in {city}, I have waited over an hour for a bus without knowing if it would come.",
        "step": "The phones of drivers would provide the location data, and the model would learn the traffic of each route.",
        "measure": "I would measure the minutes commuters save each day.",
    },
]

PRODUCT = {
    "fort": ["I would build {product}. {pain} {step} {measure}"],
    "moyen": [
        "I would create {short}. Many people in {country} face this problem every day and technology can help them. With AI the solution can be faster and cheaper. I would start with a mobile application and then expand to other countries.",
        "My idea is {short}. I think it is needed in {country} because existing solutions are expensive. I would use machine learning to improve the service over time and work with local partners.",
        "I would like to build {short}. It can have a big impact on communities. I have some experience building mobile apps, so I would begin with a prototype and test it with users.",
    ],
    "faible": [
        "I will build an app that uses AI to help people. It will be very useful.",
        "A platform with artificial intelligence for business. Many customers will pay for it.",
        "I want to create something like ChatGPT but for Africa.",
    ],
    "generique": [
        "With unlimited time and resources, I would leverage cutting-edge artificial intelligence to develop a transformative, scalable platform that empowers communities across Africa. By harnessing the power of machine learning and data-driven insights, this innovative solution would drive sustainable impact, foster inclusive growth and unlock unprecedented opportunities for all stakeholders.",
        "I would build a revolutionary AI-powered ecosystem designed to seamlessly bridge the gap between technology and everyday life. This holistic, user-centric solution would leverage state-of-the-art algorithms to deliver personalised experiences, optimise outcomes and catalyse meaningful change at scale across diverse sectors.",
    ],
}

# --------------------------------------------------------------------------
# Question 2 : une approche inhabituelle
# --------------------------------------------------------------------------

UNCONVENTIONAL = {
    "fort": [
        "In {year}, our student club had no budget for servers to run a hackathon. Instead of cancelling, I asked a cybercafe owner in {city} to lend us his machines at night in exchange for a free website. Forty students coded from 9 pm to 6 am. Three of the projects are still online, and the owner now hosts the event every year.",
        "Our final-year project needed labelled images of crop diseases and we could not afford annotators. I turned the task into a game for agriculture students: each correct label earned points toward phone credit donated by a local shop. We collected 6,000 labels in two weeks and our model reached 91% accuracy.",
        "A client refused to pay for a booking system until she saw it working. Rather than argue, I built the first version in a shared spreadsheet with automated messages and ran her salon on it for a month. She saw fewer missed appointments, paid for the real application, and referred two other salons.",
        "When our app kept crashing on old phones, the team wanted to rewrite everything. I bought the three cheapest phones in the market and made them our only test devices for two weeks. We found that images caused the crashes, compressed them, and cut crash reports by 80% without a rewrite.",
        "I could not find an internship, so I emailed twenty small businesses in {city} offering to fix one technical problem for free. Four answered. One problem, a manual stock count, became a tool that saves the shop five hours a week, and the owner hired me part-time for a year.",
        "Students in my tutoring group kept failing recursion. Explanations did not help, so I asked them to act out the call stack with chairs in the classroom. Everyone laughed, but the next test average rose from 9 to 14 out of 20, and the lecturer adopted the exercise.",
        "Our team lost its designer a week before a demo day. Instead of searching for a replacement, I interviewed five users and let them sketch the screens themselves on paper. We built exactly those screens. The jury praised the simplicity and we finished second out of thirty teams.",
        "To test demand for a tutoring service, I did not build anything. I printed a phone number on flyers near two schools in {city} and answered every call myself for ten days. Sixty-three parents called, which convinced two teachers to join me before a single line of code was written.",
    ],
    "moyen": [
        "During a group project, our code was not working before the deadline. I suggested dividing the work differently and using a new framework that I learned on YouTube. We finished on time and got a good grade.",
        "At my internship the reports were made by hand. I proposed to use a script to automate them even though nobody asked. My supervisor was happy with the result and the team still uses it.",
        "When my laptop broke before exams, I studied and coded on my phone using online tools. It was difficult but I passed all my courses and learned to adapt.",
        "Our association had few members, so I used social media challenges instead of posters to attract people. More students joined the next events.",
    ],
    "faible": [
        "I always think outside the box when there is a problem. The result is usually good.",
        "One time I solved a bug in a different way. It worked.",
        "I am a creative person and I like to find solutions.",
    ],
    "generique": [
        "Throughout my journey, I have consistently embraced innovative thinking to overcome complex challenges. By leveraging creative problem-solving methodologies and thinking outside the box, I was able to deliver impactful results that exceeded expectations. This experience underscored the importance of adaptability, resilience and a growth mindset in a dynamic and fast-paced environment.",
        "Faced with a multifaceted challenge, I adopted an unconventional, holistic approach that prioritised collaboration and strategic innovation. This transformative experience not only yielded outstanding outcomes but also reinforced my commitment to continuous learning, agility and excellence in navigating an ever-evolving technological landscape.",
    ],
}

# --------------------------------------------------------------------------
# Question 3 : mener une équipe en difficulté
# --------------------------------------------------------------------------

LEADERSHIP = {
    "fort": [
        "Two days before our app launch, the payment provider changed its API and half the team wanted to postpone. I split six people into pairs, gave each pair one failing flow, and kept a visible board of what was fixed. We launched on time. I learned that people calm down when the next step is small and clear.",
        "As class representative, I led forty students through a three-month strike by lecturers. I organised peer-taught sessions and rotated who taught so nobody felt inferior. Thirty-four of us passed the delayed exams. I learned that leadership is mostly logistics and listening.",
        "Our robotics team lost its sponsor a month before the national competition in {city}. I was honest with the team about the numbers, then asked each member to bring one idea. We sold repair services on campus and raised the fee. We reached the semi-final, and I learned to share bad news early.",
        "During a community health data project, two team members stopped speaking after a dispute about credit. I met each one alone, then rewrote our task list so every contribution was named. Work resumed within a week. I learned that conflict is often about recognition, not the task.",
        "I managed five volunteers building a school website when the head teacher rejected our first version entirely. The team was discouraged. I invited her to our next working session so they heard her reasons directly. The second version was approved in ten days. I learned to bring the user into the room.",
        "When our startup weekend team realised on Saturday night that the idea already existed, three members wanted to quit. I proposed we spend one hour calling potential users before deciding. Those calls revealed a different problem, which we pitched on Sunday. We won the audience prize.",
        "I supervised a team of eight enumerators for a survey in rural {country}. Heavy rains cut the roads and morale dropped. I reorganised the routes around motorbike taxis and paid transport in advance from my own allowance. We completed 92% of the sample. I learned that a leader removes obstacles first.",
        "Leading a remote open-source project, I saw contributions fall after a harsh code review discouraged newcomers. I wrote a short review guide, paired each newcomer with a mentor and thanked every first contribution publicly. Monthly contributors grew from four to fifteen.",
    ],
    "moyen": [
        "I was the leader of a group assignment where some members did not participate. I talked to them and gave each person a task with a deadline. In the end we submitted the work and I learned that communication is important.",
        "At my church youth group I organised an event with a small budget. Some volunteers were discouraged, but I encouraged them and we worked together. The event went well. I learned to be patient.",
        "During my internship I coordinated two other interns on a website project. We had delays because of the client. I motivated the team by reminding them of our goal and we delivered.",
        "As captain of my football team, we lost many matches at the beginning. I told the players to keep training and believe in themselves. We finished the season better.",
    ],
    "faible": [
        "I am a good leader and people follow me. I motivate my team by talking to them.",
        "I led my group in school. It was hard but we did it.",
        "Leadership is about being strong. I learned a lot.",
    ],
    "generique": [
        "As a visionary leader, I successfully guided a diverse team through a challenging situation by fostering open communication, empowering team members and cultivating a culture of trust and accountability. This experience taught me that effective leadership is rooted in empathy, strategic vision and the ability to inspire others toward a shared goal.",
        "In navigating a particularly demanding period, I leveraged emotional intelligence and collaborative synergy to keep my team aligned and motivated. By championing transparency and celebrating small wins, we achieved remarkable results. Ultimately, I learned that true leadership is about serving others and unlocking their full potential.",
    ],
}

# --------------------------------------------------------------------------
# Question 4 : la réussite
# --------------------------------------------------------------------------

SUCCESS = {
    "fort": [
        "Success means that something I built keeps working when I am not there. I measure it by use, not praise: the stock tool I wrote for a shop in {city} has run every day for a year. I also count the people I have taught who now teach others; so far there are six.",
        "For me success is choosing my own problems. I measure it each December with three questions: did I learn a skill that scared me, did I earn enough to support my family, and did the work of someone else become easier because of mine? Last year I answered yes twice.",
        "Success is keeping promises, including the ones I make to myself. I track weekly goals in a notebook and review them on Sundays. Finishing my degree while working nights was a success; abandoning my first app after two months was not, and I wrote down why.",
        "I define success as usefulness at scale. A project used by ten people who return every week matters more to me than a prize. I measure retention first, then revenue, then recognition, in that order.",
        "Success means my younger sisters see options I did not have. I measure it by concrete things: school fees paid on time, a laptop at home, and the number of girls in the coding club I started, which grew from five to twenty-two.",
        "Success is progress I can explain. Every quarter I write one page on what I can do now that I could not do before. If the page is empty, the quarter failed, whatever my grades or salary say.",
    ],
    "moyen": [
        "Success for me is achieving my goals and helping my family. I measure it by the progress I make every year in my career and my studies. I also want to have a positive impact on my community.",
        "Success means being happy with what I do and being financially independent. I measure it by my results and by the feedback from people around me.",
        "To me, success is to build a company that creates jobs. I will know I am successful when my products are used by many people.",
        "Success is never giving up. I measure it by looking at how far I have come since I started learning programming.",
    ],
    "faible": [
        "Success is money and a good life.",
        "Success means to be successful in everything I do. I measure it by my achievements.",
        "Being the best. I always want to win.",
    ],
    "generique": [
        "Success, to me, is a multifaceted journey rather than a destination. It encompasses personal growth, meaningful impact and the continuous pursuit of excellence. I measure it not merely by milestones achieved, but by the positive change I create, the resilience I demonstrate and the lasting value I bring to my community and beyond.",
        "I believe success is the harmonious alignment of purpose, passion and impact. I measure it through a holistic lens that considers personal fulfilment, professional achievement and the ability to empower others, ultimately striving to leave a legacy that inspires future generations.",
    ],
}

# --------------------------------------------------------------------------
# Question 5 : un objectif de long terme
# --------------------------------------------------------------------------

LONG_TERM = {
    "fort": [
        "For four years I have been working toward becoming a machine learning engineer without a computer science degree. I failed the first online course twice and had no laptop for eight months. I kept going by studying at a cybercafe from 6 am and by publishing every small project. My fifth project got me my first paid contract.",
        "My goal since {year} is to make our coding club the largest in the public universities of {country}. We lost our room, then our faculty adviser. What kept me going was a list of the 140 students who had already attended. We now meet on three campuses.",
        "I decided at nineteen to pay for my own studies. I sold phone accessories, repaired computers and tutored maths, and I still missed a semester for unpaid fees. I returned the next year because my younger brother was watching. I graduated in {year}.",
        "For three years I have maintained an open-source library for mobile money payments. Twice the provider changed its API without notice and users blamed me. I continued because forty small businesses depend on it and their messages remind me why it exists.",
        "I have wanted to build a hardware product since secondary school. My first two prototypes of a soil sensor failed in the field and I lost my savings. I kept the broken boards on my desk, found a mentor in {city}, and the third version has now run for six months on a farm.",
        "My long-term goal is to study and work in English although I grew up speaking French. I failed my first technical interview because I could not explain my own code. I practised by recording a five-minute explanation every day for a year. I now mentor others in English.",
    ],
    "moyen": [
        "My long-term goal is to become a software engineer. I had many difficulties like lack of money and bad internet connection, but I continued to learn online. My passion for technology kept me going.",
        "I wanted to finish my degree even when it was hard to pay fees. I worked during holidays and my family supported me. I am proud that I did not give up.",
        "My goal is to start my own company. I tried a small business before and it failed, but I learned from the mistakes. I believe that with the right training I will succeed.",
        "I have been learning programming for three years. Sometimes I wanted to stop because it was too difficult, but my friends encouraged me and I continued.",
    ],
    "faible": [
        "My goal is to be rich. I never give up.",
        "I want to be a great developer. God is my strength.",
        "I had setbacks but I continued. That is my story.",
    ],
    "generique": [
        "My long-term goal has always been to harness the transformative power of technology to drive sustainable development across Africa. Despite numerous obstacles, my unwavering determination, passion for innovation and steadfast belief in my vision have kept me going. Each setback has served as a valuable stepping stone toward growth.",
        "Throughout my journey, I have remained steadfastly committed to my overarching goal of becoming a catalyst for positive change. In the face of adversity, I drew strength from my resilience, my supportive network and my deep-seated conviction that perseverance ultimately paves the way to success.",
    ],
}

ESSAY_POOLS = [PRODUCT, UNCONVENTIONAL, LEADERSHIP, SUCCESS, LONG_TERM]

# --------------------------------------------------------------------------
# Transcriptions des vidéos (tiennent lieu de sortie de la reconnaissance vocale)
# --------------------------------------------------------------------------

STATEMENT_REASON = [
    "I want to turn {short} into a real company, and I cannot do it alone or without business training",
    "I have built products but never a business, and MEST is the only program I know that teaches both and gives a full year to do it",
    "I am looking for co-founders who are as serious about building in West Africa as I am",
    "after three years of freelancing I want to build something that outlives a client contract",
]
STATEMENT_MOMENT = [
    "a shop owner paid me for a small stock tool and told me it changed his week",
    "I saw sixty parents call a number on a flyer for a service that did not exist yet",
    "my first app reached two hundred users without any advertising",
    "I realised that the problems I complained about every day were business ideas",
]
STATEMENT_GAIN = [
    "What I hope to gain that I cannot get elsewhere is a full year of training with a team around me, and investors who understand African markets.",
    "From MEST I want honest feedback on my ideas, co-founders with skills I lack, and the discipline of building for real customers.",
    "No other program near me combines technical training, business coaching and seed funding, and that is exactly what I need.",
]
STATEMENT = {
    "fort": [
        "Hello, my name is {first_name} and I am from {country}. I am applying to the MEST AI Startup Program because {reason}. The moment I knew I wanted to be an entrepreneur was when {moment}. I studied {major} at {institution} and I have worked as {a_job_title} at {organisation}. I mostly work with {skills}. {gain} Thank you for considering my application.",
    ],
    "moyen": [
        "Hello, I am {first_name} from {country}. I am applying to MEST because I want to become an entrepreneur and learn more about artificial intelligence. I have liked technology since I was young. I studied {major} and I have some experience with {skills}. I hope to gain knowledge, a network and funding. Thank you for this opportunity.",
        "Good day. My name is {first_name}. I want to join the MEST AI Startup Program to improve my skills and start a company in {country}. I decided to become an entrepreneur because there are many problems to solve here. I worked as {a_job_title}. I believe MEST will give me the training I need. Thank you.",
    ],
    "faible": [
        "Hi, my name is {first_name}. I want to join MEST because it is a good program. I want to start a business. I know programming a little. Thank you.",
        "Hello. I am {first_name}. I am applying because I need this opportunity. I will work hard. Thanks.",
    ],
    "generique": [
        "Hello, my name is {first_name}. I am deeply passionate about leveraging technology to create transformative impact across Africa. I am applying to the MEST AI Startup Program because it represents an unparalleled opportunity to harness my potential, cultivate an entrepreneurial mindset and drive innovation. My journey has equipped me with a robust skill set and an unwavering commitment to excellence. I am confident that this program will empower me to unlock new horizons. Thank you.",
    ],
    "inaudible": [
        "[inaudible] my name is {first_name} [inaudible] applying to [inaudible] program because [noise] [inaudible] entrepreneur [inaudible] experience in [inaudible] [noise] thank you.",
    ],
}
REFLECTION = {
    "fort": [
        "The assessment was harder than I expected. The logic section went well and I finished it early. I struggled with the probability questions and ran out of time on the last coding task, so I left one test case failing. What surprised me was how much reading the business cases required. Next time I would read all the questions first.",
        "I felt focused during the assessment and a little tired after it. The coding questions went well because they were close to my daily work. I struggled with the numerical reasoning under time pressure and guessed two answers. I found the situational questions interesting because there was no obvious right answer.",
    ],
    "moyen": [
        "The assessment was okay. Some questions were difficult, especially the coding part. I think I did well in the reasoning section. I felt stressed because of the time but I finished. It was an interesting experience.",
        "I was nervous at the beginning. The first part went well. I struggled with some technical questions that I had not seen before. Overall I learned that I need to practise more.",
    ],
    "faible": [
        "The test was hard. I did my best. Thank you.",
        "It was fine. Some questions I did not understand.",
    ],
    "rapide": [
        "The assessment was easy for me and I finished very quickly. All the questions were simple.",
    ],
}

# --------------------------------------------------------------------------
# Pièces jointes
# --------------------------------------------------------------------------

CERTIFICATE_TITLES = [
    ("Certificate of Completion", "{training}"),
    ("Certificate of Participation", "Developer Festival {city} {year}"),
    ("Hackathon Finalist", "{city} Tech Week {year}"),
    ("Certificate of Achievement", "Student Ambassador Programme {year}"),
]

RESUME_HEADLINES = {
    "fort": ["Software Engineer", "Mobile Developer", "Machine Learning Engineer", "Full Stack Developer"],
    "moyen": ["Junior Developer", "Web Developer", "IT Graduate"],
    "faible": ["Graduate", "Aspiring Entrepreneur"],
}
RESUME_BULLETS = {
    "fort": [
        "Built a REST API serving 4,000 monthly users and cut average response time from 900 ms to 250 ms.",
        "Shipped a mobile app with offline mode, rated 4.5 by 300 users on the store.",
        "Trained an image classification model reaching 91% accuracy on 6,000 labelled photos.",
        "Automated weekly sales reports, saving the team five hours a week.",
        "Led a team of four developers through two product releases.",
        "Maintained an open-source payments library used by forty small businesses.",
    ],
    "moyen": [
        "Developed web pages and fixed bugs reported by clients.",
        "Assisted the team in testing a mobile application before release.",
        "Maintained the company website and trained two colleagues.",
        "Wrote scripts to clean customer data.",
    ],
    "faible": [
        "Helped with daily office tasks.",
        "Worked with customers and the sales team.",
    ],
}
