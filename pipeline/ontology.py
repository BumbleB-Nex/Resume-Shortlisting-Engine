"""
Skill ontology — aliases and partial (related) relations.

Scoped to the Full-Stack / general software engineering domain that the
InternLoom JD lives in. Matching is word-boundary aware so short aliases
like "js" or "ml" never match inside unrelated words.
"""
from __future__ import annotations

import re
from functools import lru_cache

from config import ONTOLOGY_RELATED_CREDIT


class SkillOntology:
    # canonical → aliases. A hit on canonical text is EXACT, on an alias is ALIAS.
    ALIASES: dict[str, list[str]] = {
        "javascript": ["js", "es6", "es6+", "es2015", "es2016", "ecmascript", "vanilla js",
                       "modern javascript"],
        "typescript": ["ts"],
        "python": ["python3", "python 3", "py"],
        "java": [],
        "c++": ["cpp"],
        "c#": ["csharp", "c sharp"],
        "node.js": ["nodejs", "node js", "node"],
        "react": ["reactjs", "react.js", "react js"],
        "react native": ["react-native"],
        "next.js": ["nextjs", "next js"],
        "vue": ["vuejs", "vue.js", "vue js"],
        "angular": ["angularjs", "angular.js"],
        "express": ["expressjs", "express.js", "express js"],
        "mongodb": ["mongo", "mongoose"],
        "postgresql": ["postgres", "psql", "pg"],
        "mysql": ["my sql"],
        "sql": ["structured query language", "sql queries", "sql databases",
                "relational databases", "relational database"],
        "nosql": ["no sql", "no-sql"],
        "html": ["html5"],
        "css": ["css3", "sass", "scss"],
        "html/css": ["html5", "css3", "html & css", "html and css", "html, css"],
        "tailwind": ["tailwind css", "tailwindcss"],
        "bootstrap": [],
        "docker": ["containerization", "containerisation", "containers", "dockerfile"],
        "kubernetes": ["k8s"],
        "git": ["github", "gitlab", "bitbucket", "version control", "vcs",
                "github workflows", "git workflows", "git/github"],
        "rest api": ["rest apis", "restful api", "restful apis", "rest services",
                     "http api", "web api", "web apis", "api development",
                     "restful services", "restful web services", "apis", "api",
                     "restful", "backend api", "backend apis"],
        "graphql": [],
        "json": [],
        "sqlite": [],
        "svelte": [],
        "pytorch": [],
        "tensorflow": ["tf"],
        "keras": [],
        "scikit-learn": ["sklearn", "scikit learn"],
        "pandas": [],
        "numpy": [],
        "redis": [],
        "nginx": [],
        "heroku": [],
        "vercel": [],
        "netlify": [],
        "cloud deployment": ["cloud platform", "cloud platforms", "cloud services",
                             "cloud hosting", "cloud infrastructure", "cloud computing"],
        "nosql databases": ["nosql database", "nosql db", "document database", "document store"],
        "frontend framework": ["frontend frameworks", "front-end framework", "front-end frameworks",
                               "javascript framework", "javascript frameworks", "ui framework"],
        "backend development": ["backend", "back-end", "backend services", "server-side",
                                "server side"],
        "frontend development": ["frontend", "front-end", "client-side", "ui development"],
        "full stack development": ["full stack", "full-stack", "fullstack", "mern", "mern stack",
                                   "mean stack"],
        "debugging": ["troubleshooting", "troubleshoot", "debug", "bug fixing"],
        "code review": ["code reviews", "peer review", "pull requests", "pull request"],
        "database design": ["database schema", "schema design", "data modelling", "data modeling",
                            "database schemas"],
        # ── data / analytics ─────────────────────────────────────────
        "data pipelines": ["data pipeline", "etl", "elt", "etl pipelines", "etl processing",
                           "data ingestion", "data workflows"],
        "data warehouse": ["data warehouses", "data warehousing", "cloud data warehouse"],
        "snowflake": [], "redshift": ["amazon redshift"], "bigquery": ["google bigquery"],
        "airflow": ["apache airflow"], "azkaban": [], "dbt": [], "fivetran": [], "matillion": [],
        "stitch": [],
        "spark": ["apache spark", "pyspark"], "hadoop": ["hdfs", "mapreduce"], "hive": ["apache hive"],
        "presto": ["trino"], "kafka": ["apache kafka"], "distributed computing": ["big data",
                                                                                 "large data sets",
                                                                                 "large datasets"],
        "scala": [], "bash": ["shell scripting", "shell script", "bash scripting"],
        "cassandra": [], "neo4j": [], "dynamodb": [],
        "statistics": ["statistical analysis", "statistical modelling", "statistical modeling",
                       "probability", "hypothesis testing", "a/b testing"],
        "data visualization": ["data visualisation", "dashboards", "dashboarding"],
        "tableau": [], "power bi": ["powerbi"], "matplotlib": [], "seaborn": [], "plotly": [],
        "excel": ["ms excel", "microsoft excel", "spreadsheets", "google sheets"],
        "jupyter": ["jupyter notebook", "jupyter notebooks", "google colab", "colab"],
        "nlp": ["natural language processing", "text mining", "transformers", "llm", "llms"],
        "computer vision": ["opencv", "image processing"],
        "data analysis": ["data analytics", "exploratory data analysis", "eda"],
        "kaggle": ["kaggle competitions"],
        "r": ["r programming", "rstudio"],
        # ── marketing / content ──────────────────────────────────────
        "digital marketing": ["online marketing", "digital marketing campaigns",
                              "marketing campaigns", "digital campaigns"],
        "social media marketing": ["social media", "social media management", "social media campaigns",
                                   "instagram", "facebook", "twitter", "linkedin marketing",
                                   "social channels", "social media intern"],
        "content creation": ["content creator", "digital content", "content marketing",
                             "content strategy", "producing content", "creating content"],
        "copywriting": ["copy writing", "ad copy", "blog writing", "blog posts", "newsletters",
                        "writing skills", "proofreading", "proof reading"],
        "seo": ["search engine optimization", "search engine optimisation", "sem", "keyword research"],
        "google analytics": ["ga4", "web analytics", "digital analytics"],
        "google ads": ["adwords", "google adwords", "paid ads", "paid advertising", "ppc", "meta ads",
                       "facebook ads", "paid social"],
        "email marketing": ["mailchimp", "hubspot", "email campaigns", "newsletter marketing"],
        "cms": ["content management system", "content management systems", "wordpress", "umbraco",
                "drupal", "web content management"],
        "hootsuite": ["agorapulse", "buffer", "sprout social", "social media scheduling"],
        "canva": [],
        "photography": ["photo editing", "editing images", "image editing"],
        "graphic design": ["graphics", "visual design", "creating graphics", "design skills"],
        "photoshop": ["adobe photoshop"], "illustrator": ["adobe illustrator"],
        "adobe creative suite": ["adobe creative cloud", "adobe suite", "adobe tools", "adobe"],
        "ui/ux": ["ui ux", "ux design", "ui design", "user experience", "user interface design",
                  "wireframing", "prototyping"],
        # ── video / media ────────────────────────────────────────────
        "video editing": ["video editor", "editing videos", "video production", "post-production",
                          "post production", "editing footage", "raw footage", "rough cut"],
        "premiere pro": ["adobe premiere", "adobe premiere pro", "premiere"],
        "after effects": ["adobe after effects", "motion graphics", "special effects", "vfx"],
        "final cut pro": ["final cut", "fcp", "fcpx"],
        "davinci resolve": ["davinci", "color grading", "colour grading"],
        "avid": ["avid media composer", "media composer"],
        "sound design": ["audio editing", "sound editing", "audio mixing", "sound effects"],
        "videography": ["filming", "camera operation", "cinematography", "shooting"],
        "youtube": ["youtube channel", "video marketing"],
        # ── general software ─────────────────────────────────────────
        "c": ["c programming", "c language"],
        "kotlin": [], "swift": [], "flutter": [], "dart": [],
        "android": ["android development", "android studio"], "ios": ["ios development"],
        "selenium": [], "cypress": [], "jira": [], "confluence": [],
        "cybersecurity": ["cyber security", "information security", "infosec", "network security",
                          "penetration testing", "pentesting", "ethical hacking", "vulnerability assessment"],
        "networking": ["tcp/ip", "computer networks", "network administration", "ccna"],
        "project management": ["project planning", "organizational skills", "organisational skills",
                               "project coordination"],
        "product management": ["product roadmap", "product strategy", "user stories"],
        "sales": ["lead generation", "cold calling", "business development", "crm", "salesforce"],
        "customer support": ["customer service", "customer success", "helpdesk", "it support",
                             "technical support", "troubleshooting hardware"],
        "machine learning": ["ml", "supervised learning", "unsupervised learning"],
        "deep learning": ["dl", "neural networks"],
        "artificial intelligence": ["ai"],
        "aws": ["amazon web services", "amazon aws", "ec2", "s3", "aws lambda"],
        "azure": ["microsoft azure"],
        "gcp": ["google cloud", "google cloud platform"],
        "ci/cd": ["continuous integration", "continuous deployment",
                  "github actions", "jenkins", "circleci", "ci cd"],
        "linux": ["ubuntu", "unix"],
        "agile": ["scrum", "agile methodology", "agile methodologies"],
        "unit testing": ["jest", "pytest", "mocha", "junit", "testing frameworks"],
        "firebase": [],
        "redux": [],
        "jquery": [],
        "flask": [],
        "django": [],
        "fastapi": [],
        "spring boot": ["spring", "springboot"],
        "oop": ["object oriented programming", "object-oriented programming",
                "object oriented"],
        "data structures": ["dsa", "data structures and algorithms", "algorithms"],
        "figma": [],
        "postman": [],
        "vs code": ["vscode", "visual studio code"],
        "websockets": ["websocket", "socket.io"],
        "authentication": ["jwt", "oauth", "auth"],
        "responsive design": ["responsive web design", "mobile-first",
                              "responsive ui", "responsive"],
    }

    # related skill → list of canonical requirements it partially satisfies
    PARTIAL: dict[str, list[str]] = {
        "express":       ["node.js", "rest api"],
        "fastapi":       ["rest api", "python"],
        "flask":         ["rest api", "python"],
        "django":        ["rest api", "python"],
        "spring boot":   ["rest api", "java"],
        "next.js":       ["react"],
        "vue":           ["react"],
        "angular":       ["react"],
        "react native":  ["react"],
        "svelte":        ["react"],
        "sqlite":        ["postgresql", "sql", "mysql"],
        "mysql":         ["postgresql", "sql"],
        "postgresql":    ["mysql", "sql"],
        "mongodb":       ["nosql"],
        "firebase":      ["nosql", "mongodb"],
        "kubernetes":    ["docker"],
        "mongoose":      ["mongodb"],
        "pytorch":       ["machine learning", "deep learning"],
        "tensorflow":    ["machine learning", "deep learning"],
        "keras":         ["machine learning", "deep learning"],
        "scikit-learn":  ["machine learning"],
        "sklearn":       ["machine learning"],
        "pandas":        ["python"],
        "numpy":         ["python"],
        "typescript":    ["javascript"],
        "javascript":    ["typescript"],
        "jquery":        ["javascript"],
        "graphql":       ["rest api"],
        "bootstrap":     ["css", "html/css", "responsive design"],
        "tailwind":      ["css", "html/css", "responsive design"],
        "azure":         ["aws"],
        "gcp":           ["aws"],
        "jest":          ["unit testing"],
        "pytest":        ["unit testing"],
        "socket.io":     ["websockets"],
        "aws":           ["cloud deployment"],
        "heroku":        ["cloud deployment"],
        "vercel":        ["cloud deployment"],
        "netlify":       ["cloud deployment"],
        "firebase":      ["nosql", "mongodb", "cloud deployment", "nosql databases"],
        "mongodb":       ["nosql", "nosql databases"],
        "redis":         ["nosql databases"],
        "react":         ["frontend framework", "frontend development", "javascript"],
        "vue":           ["react", "frontend framework", "frontend development", "javascript"],
        "angular":       ["react", "frontend framework", "frontend development", "javascript"],
        "next.js":       ["react", "frontend framework", "javascript"],
        "svelte":        ["react", "frontend framework", "javascript"],
        "node.js":       ["backend development", "javascript"],
        "express":       ["node.js", "rest api", "backend development", "javascript"],
        "redux":         ["react", "javascript"],
        "django":        ["rest api", "python", "backend development"],
        "flask":         ["rest api", "python", "backend development"],
        "fastapi":       ["rest api", "python", "backend development"],
        "spring boot":   ["rest api", "java", "backend development"],
        "full stack development": ["frontend development", "backend development"],
        "postman":       ["rest api"],
        "html":          ["html/css"],
        "css":           ["html/css"],
        "html/css":      ["html", "css"],
        # data
        "pandas":        ["python", "data analysis"],
        "numpy":         ["python", "data analysis"],
        "matplotlib":    ["data visualization", "python"],
        "seaborn":       ["data visualization", "python"],
        "plotly":        ["data visualization"],
        "tableau":       ["data visualization", "power bi"],
        "power bi":      ["data visualization", "tableau"],
        "snowflake":     ["data warehouse", "sql"],
        "redshift":      ["data warehouse", "sql", "aws"],
        "bigquery":      ["data warehouse", "sql", "gcp"],
        "airflow":       ["data pipelines"],
        "dbt":           ["data pipelines", "sql"],
        "fivetran":      ["data pipelines"],
        "matillion":     ["data pipelines"],
        "spark":         ["distributed computing", "data pipelines"],
        "hadoop":        ["distributed computing"],
        "hive":          ["distributed computing", "sql"],
        "presto":        ["distributed computing", "sql"],
        "kafka":         ["data pipelines"],
        "cassandra":     ["nosql databases", "nosql"],
        "neo4j":         ["nosql databases", "nosql"],
        "dynamodb":      ["nosql databases", "nosql", "aws"],
        "scikit-learn":  ["machine learning", "data analysis"],
        "nlp":           ["machine learning", "deep learning"],
        "computer vision": ["machine learning", "deep learning"],
        "kaggle":        ["machine learning", "data analysis"],
        "excel":         ["data analysis"],
        "jupyter":       ["python"],
        # marketing / design / video
        "hootsuite":     ["social media marketing"],
        "canva":         ["graphic design", "content creation"],
        "photoshop":     ["graphic design", "adobe creative suite", "photography"],
        "illustrator":   ["graphic design", "adobe creative suite"],
        "figma":         ["ui/ux", "graphic design"],
        "google ads":    ["digital marketing"],
        "seo":           ["digital marketing"],
        "email marketing": ["digital marketing"],
        "social media marketing": ["digital marketing", "content creation"],
        "copywriting":   ["content creation"],
        "google analytics": ["digital marketing", "data analysis"],
        "cms":           ["content creation"],
        "premiere pro":  ["video editing", "adobe creative suite"],
        "after effects": ["video editing", "adobe creative suite"],
        "final cut pro": ["video editing"],
        "davinci resolve": ["video editing"],
        "avid":          ["video editing"],
        "videography":   ["video editing"],
        "youtube":       ["content creation", "social media marketing"],
        # general
        "azure":         ["aws", "cloud deployment"],
        "gcp":           ["aws", "cloud deployment"],
        "kotlin":        ["android", "java"],
        "swift":         ["ios"],
        "flutter":       ["android", "ios"],
        "react native":  ["react", "android", "ios"],
        "selenium":      ["unit testing"],
        "cypress":       ["unit testing"],
    }

    # Soft skills — scored, but never allowed to block a candidate as a must-have.
    SOFT_SKILLS: dict[str, list[str]] = {
        "communication": ["communication skills", "verbal communication", "written communication",
                          "communicate", "communicating"],
        "problem solving": ["problem-solving", "problem solving skills", "analytical skills",
                            "analytical thinking", "analytical"],
        "teamwork": ["team player", "collaboration", "collaborative", "team work",
                     "work in a team", "cross-functional"],
        "leadership": ["led a team", "team lead", "leading"],
        "time management": ["deadlines", "prioritisation", "prioritization"],
        "attention to detail": ["detail-oriented", "detail oriented"],
        "adaptability": ["adaptable", "fast learner", "quick learner", "eager to learn",
                         "willingness to learn", "learning mindset", "self-motivated",
                         "self motivated", "proactive"],
        "critical thinking": [],
    }

    # pairs that should collapse into one requirement when both appear in a JD line
    MERGE: dict[frozenset, str] = {frozenset({"html", "css"}): "html/css"}

    # generic umbrella terms — useful as alternatives, redundant beside a concrete skill
    UMBRELLA = {"backend development", "frontend development", "frontend framework",
                "cloud deployment", "nosql databases", "full stack development", "nosql",
                "adobe creative suite", "data visualization", "distributed computing",
                "data warehouse", "cms", "digital marketing"}

    def __init__(self) -> None:
        # soft skills participate in matching like any other skill
        self.ALIASES = {**SkillOntology.ALIASES, **SkillOntology.SOFT_SKILLS}
        self._alias_to_canonical: dict[str, str] = {}
        for canonical, aliases in self.ALIASES.items():
            self._alias_to_canonical[canonical] = canonical
            for a in aliases:
                self._alias_to_canonical.setdefault(a, canonical)
        # one alternation regex, longest forms first so "react native" wins over "react"
        forms = sorted((f for f in self._alias_to_canonical if len(f) >= 2), key=len, reverse=True)
        self._combined = re.compile(
            r"(?<![a-z0-9+#])(?:" + "|".join(re.escape(f) for f in forms) + r")(?![a-z0-9+#])")

    def is_soft(self, skill: str) -> bool:
        return self.canonicalize(skill) in self.SOFT_SKILLS

    def find_forms(self, text: str) -> dict[str, set[str]]:
        """canonical skill → set of surface forms found in `text` (single regex pass)."""
        found: dict[str, set[str]] = {}
        for m in self._combined.finditer(self.normalize(text)):
            form = m.group(0)
            found.setdefault(self._alias_to_canonical[form], set()).add(form)
        for pair, merged in self.MERGE.items():
            if pair.issubset(found):
                found.setdefault(merged, set()).update(*(found[p] for p in pair))
        return found

    def find_skills(self, text: str) -> list[str]:
        """
        Canonical skills mentioned in `text`, in order of appearance.
        Greedy longest-match, non-overlapping; html+css collapse to html/css.
        """
        t = self.normalize(text)
        ordered = list(dict.fromkeys(self._alias_to_canonical[m.group(0)] for m in self._combined.finditer(t)))
        for pair, merged in self.MERGE.items():
            if pair.issubset(ordered):
                idx = min(ordered.index(p) for p in pair)
                ordered = [c for c in ordered if c not in pair]
                ordered.insert(idx, merged)
        return ordered

    def match_from_mentions(self, terms: list[str], mentions: dict[str, set[str]]) -> tuple[float, str]:
        """
        Fast `match_any` using a precomputed `find_forms` result.
          EXACT   the requirement's own text appears
          ALIAS   an alias of the requirement (or of an alternative) appears
          RELATED a related technology appears
        """
        if not mentions:
            return (0.0, "NO_MATCH")
        best: tuple[float, str] = (0.0, "NO_MATCH")
        for term in terms:
            norm = self.normalize(term)
            canonical = self.canonicalize(norm)
            forms = mentions.get(canonical)
            if forms:
                if norm in forms:
                    return (1.0, "EXACT")
                best = (1.0, "ALIAS")
        if best[0] > 0:
            return best
        for term in terms:
            for related in self.related_skills(term):
                if related in mentions:
                    return (ONTOLOGY_RELATED_CREDIT, "RELATED")
        return best

    # ------------------------------------------------------------------
    @staticmethod
    def normalize(text: str) -> str:
        text = text.lower().replace("\u2019", "'")
        text = re.sub(r"[\u2013\u2014]", "-", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    @lru_cache(maxsize=4096)
    def _pattern(term: str) -> re.Pattern:
        # word-boundary that treats letters/digits/+/# as word chars so
        # "js" doesn't hit "json" and "c++" is matched whole.
        esc = re.escape(term)
        return re.compile(rf"(?<![a-z0-9+#]){esc}(?![a-z0-9+#])")

    def contains(self, term: str, text_norm: str) -> bool:
        return bool(self._pattern(self.normalize(term)).search(text_norm))

    # ------------------------------------------------------------------
    def canonicalize(self, text: str) -> str:
        """Map an alias to its canonical key ('nodejs' → 'node.js')."""
        t = self.normalize(text)
        return self._alias_to_canonical.get(t, t)

    def is_known_skill(self, text: str) -> bool:
        t = self.normalize(text)
        if t in self.ALIASES or t in self.PARTIAL:
            return True
        return any(t in aliases for aliases in self.ALIASES.values())

    def get_all_forms(self, skill: str) -> list[str]:
        canonical = self.canonicalize(skill)
        forms = [canonical] + list(self.ALIASES.get(canonical, []))
        if canonical != self.normalize(skill):
            forms.append(self.normalize(skill))
        return list(dict.fromkeys(forms))

    def related_skills(self, requirement: str) -> list[str]:
        canonical = self.canonicalize(requirement)
        return [s for s, targets in self.PARTIAL.items() if canonical in targets]

    def match(self, requirement: str, text: str) -> tuple[float, str]:
        """
        Does `text` demonstrate `requirement`?
          (1.0, "EXACT")    requirement text found verbatim
          (1.0, "ALIAS")    a known alias found
          (0.6, "RELATED")  a related technology found
          (0.0, "NO_MATCH")
        """
        req_norm = self.normalize(requirement)
        text_norm = self.normalize(text)
        canonical = self.canonicalize(req_norm)

        if self.contains(req_norm, text_norm):
            return (1.0, "EXACT")
        if canonical != req_norm and self.contains(canonical, text_norm):
            return (1.0, "ALIAS")
        for alias in self.ALIASES.get(canonical, []):
            if self.contains(alias, text_norm):
                return (1.0, "ALIAS")
        for related in self.related_skills(canonical):
            for form in self.get_all_forms(related):
                if self.contains(form, text_norm):
                    return (ONTOLOGY_RELATED_CREDIT, "RELATED")
        return (0.0, "NO_MATCH")

    def match_any(self, terms: list[str], text: str) -> tuple[float, str]:
        """Best `match` over a requirement and its alternatives."""
        best: tuple[float, str] = (0.0, "NO_MATCH")
        rank = {"EXACT": 3, "ALIAS": 2, "RELATED": 1, "NO_MATCH": 0}
        for term in terms:
            score, mtype = self.match(term, text)
            if (score, rank[mtype]) > (best[0], rank[best[1]]):
                best = (score, mtype)
                if mtype == "EXACT":
                    break
        return best

    def found_forms(self, requirement: str, text: str) -> list[str]:
        """All forms (canonical/alias/related) of the requirement present in text."""
        text_norm = self.normalize(text)
        canonical = self.canonicalize(requirement)
        hits = [f for f in self.get_all_forms(canonical) if self.contains(f, text_norm)]
        for related in self.related_skills(canonical):
            hits += [f for f in self.get_all_forms(related) if self.contains(f, text_norm)]
        return list(dict.fromkeys(hits))


_ONTOLOGY: SkillOntology | None = None


def get_ontology() -> SkillOntology:
    global _ONTOLOGY
    if _ONTOLOGY is None:
        _ONTOLOGY = SkillOntology()
    return _ONTOLOGY
