---
name: cv-builder
description: >
  Create modern, impactful, ATS-optimized CVs and resumes, especially for IT, AI/ML, and software engineering roles.
  Use when the user asks to: create a CV, build a resume, write a curriculum vitae, optimize a resume for a job description,
  rewrite experience bullets, tailor a CV for a specific role, create a tech resume, write a cover letter,
  or improve/review an existing CV. Supports STAR, XYZ (Google), CAR frameworks, ATS optimization,
  quantification, and job-specific tailoring. Handles both fresh creation and optimization of existing CVs.
  Special focus on Full Stack Development, AI/ML Engineering, and Forward Deployed Engineer (FDE) positions.
---

# CV Builder

Build powerful, ATS-friendly CVs/resumes optimized for IT, AI/ML, and software engineering roles.

## Workflow

### 1. Gather Information

Collect from the user:
- **Target role and company** (or job description text)
- **Professional experience** (roles, dates, responsibilities, achievements)
- **Technical skills** (languages, frameworks, tools, cloud platforms)
- **Education** (degrees, institutions, graduation years)
- **Projects** (personal, open-source, Kaggle, publications)
- **Certifications** (cloud, AI/ML, DevOps)
- **Career level** (junior/mid/senior/lead/executive)
- **Target geography** (US, UK, EU -- affects format, see section 6)

If the user provides a job description, extract keywords and tailor the entire CV to match.

### 2. Choose the Right Framework for Bullets

Use the **Google XYZ formula** as the default for all experience bullets:

```
Accomplished [X] as measured by [Y] by doing [Z]
```

For complex, multi-stakeholder achievements, use **STAR** (Situation, Task, Action, Result).
For problem-solving emphasis, use **CAR** (Challenge, Action, Result).

See [references/frameworks.md](references/frameworks.md) for detailed guidance, examples, and when to use each.

### 3. Structure the CV

**Recommended section order (experienced professionals):**

1. **Contact Info** -- Name, phone, email, LinkedIn URL, GitHub URL, portfolio (optional), city
2. **Professional Summary** -- 3-4 sentences: identity + differentiator + proof + alignment
3. **Technical Skills** -- Categorized (Languages, Frameworks, Cloud, Data, Tools)
4. **Work Experience** -- Reverse chronological, 3-5 XYZ bullets per role
5. **Projects** -- For AI/ML roles; can be above Experience for juniors
6. **Education** -- Degree, institution, year; GPA only if >3.5 and <3 years out
7. **Certifications** -- Ordered by relevance to target role
8. **Publications** -- If applicable (papers, conferences, citations)

**For juniors/career changers:** Move Education, Projects, Certifications above Experience.

### 4. Write Each Section

#### Professional Summary

Structure: `[Title] + [years] + [domain] + [key achievement with metric] + [alignment to target role]`

Example:
> Machine Learning Engineer with 5+ years building production NLP and computer vision systems. Designed and deployed a real-time fraud detection pipeline serving 4M daily transactions with 99.2% precision at sub-100ms latency. Passionate about MLOps and bridging the gap between research prototypes and scalable production systems.

#### Technical Skills

Categorize -- never a flat wall of text:

```
Languages:        Python, Go, TypeScript, SQL, C++
ML Frameworks:    PyTorch, TensorFlow, Keras, scikit-learn, Hugging Face Transformers
Cloud & MLOps:    AWS (SageMaker, Lambda, S3), GCP (Vertex AI), Docker, Kubernetes
Data:             Apache Spark, Airflow, dbt, PostgreSQL, MongoDB
Tools:            Git, MLflow, Weights & Biases, Jupyter, Linux
```

Only list skills the user can discuss confidently in an interview.

#### Experience Bullets

Rules:
- Start every bullet with a strong action verb (see [references/action-verbs.md](references/action-verbs.md))
- Quantify at least 60% of bullets with numbers, percentages, dollar amounts, or timeframes
- Never repeat the same verb in consecutive bullets
- Past tense for previous roles, present tense for current role
- No personal pronouns ("I", "my")
- 3-5 bullets per role; top bullet = strongest achievement

#### Projects Section (especially for AI/ML)

Format each project:
```
[Project Name] | [Tech Stack]                                    [Date]
- One-sentence description of what was built and why
- Model/system performance: "Achieved [metric] of [value] on [dataset]"
- Deployment: "Deployed to [platform] serving [N] predictions/day at [latency]"
- Impact: [business outcome with number]
- Link: github.com/user/repo
```

### 5. ATS Optimization

These rules are mandatory for every CV produced:

- **Single-column layout** -- no tables, text boxes, multi-column, or graphics
- **Standard section headers** -- "Experience", "Skills", "Education" (not creative alternatives)
- **Contact info in body** -- never in document headers/footers
- **Standard fonts** -- Arial, Calibri, Aptos, Georgia (10-12pt body, 14-16pt headers)
- **File format** -- .docx or text-based PDF
- **Keywords** -- Mirror 15-25 keywords from the job description; use both acronyms and full forms ("Natural Language Processing (NLP)")
- **Include exact job title** from posting in Summary or Experience (10.6x higher interview rate)

See [references/ats-optimization.md](references/ats-optimization.md) for the complete ATS checklist and keyword strategy.

### 6. Geography-Specific Formatting

| Target | Format | Photo | Length |
|--------|--------|-------|--------|
| US / FAANG | 1-page resume, no photo | Never | 1 page |
| UK | British CV, no photo | Never | 2 pages |
| EU institutions | Europass | Optional | 2+ pages |
| Germany (private) | CV with professional photo | Yes | 2 pages |
| France (private) | CV, photo optional | Common | 1-2 pages |
| Tech startups (any) | US-style resume | Never | 1 page |

### 7. Length Rules

- **< 5 years experience or FAANG**: 1 page, no exceptions
- **7-10+ years**: 2 pages acceptable if every line adds value
- **Never 3 pages** for industry roles
- Second page must be at least half full

### 8. Quality Checklist

Before delivering any CV, verify:

- [ ] Professional Summary customized for target role
- [ ] Every bullet starts with a strong action verb
- [ ] 60%+ of bullets contain quantified results
- [ ] Technical skills categorized and prioritized for target role
- [ ] Single-column, ATS-safe layout
- [ ] 15-25 keywords from job description present
- [ ] No buzzwords/cliches (see [references/common-mistakes.md](references/common-mistakes.md))
- [ ] Consistent date formatting throughout
- [ ] No "References available upon request"
- [ ] LinkedIn, GitHub URLs included

### 9. Tailoring Per Job Description

When the user provides a job description:

1. Extract required skills, preferred qualifications, repeated keywords, and tools mentioned
2. Update Professional Summary to address the employer's primary needs
3. Reorder bullets -- most relevant achievements first under each role
4. Lead Skills section with skills from the posting
5. Mirror exact terminology from the posting
6. Aim for 80%+ ATS match rate

Maintain a "master CV" approach: keep all experiences, tailor by pruning/reordering per application.

### 10. Role-Specific Guidance

For these priority roles, consult [references/role-profiles.md](references/role-profiles.md) which contains:
- **Full Stack Developer/Engineer** -- skills to highlight, bullet examples, summary templates
- **AI/ML Engineer** -- production ML focus, GenAI/LLM keywords, MLOps emphasis
- **Forward Deployed Engineer (FDE)** -- client deployment format, technical consulting emphasis, "Key Deployments" section

The role profiles include ready-to-use XYZ bullet examples, summary templates, skill categories, and guidance on what recruiters specifically look for in each role.

## Reference Files

- [references/frameworks.md](references/frameworks.md) -- STAR, XYZ, CAR, PAR frameworks with examples and decision guide
- [references/action-verbs.md](references/action-verbs.md) -- 150+ action verbs categorized for tech roles
- [references/ats-optimization.md](references/ats-optimization.md) -- Complete ATS rules, keyword strategy, formatting checklist
- [references/ai-it-keywords.md](references/ai-it-keywords.md) -- AI/ML/IT keywords, certifications, and project showcase patterns
- [references/common-mistakes.md](references/common-mistakes.md) -- Buzzwords to avoid, structural mistakes, and fixes
- [references/role-profiles.md](references/role-profiles.md) -- Full Stack, AI Engineer, and FDE role-specific profiles with examples
