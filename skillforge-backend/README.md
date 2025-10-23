# skillforge-api

[![Release](https://img.shields.io/github/v/release/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api)](https://img.shields.io/github/v/release/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api)
[![Build status](https://img.shields.io/github/actions/workflow/status/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api/main.yml?branch=main)](https://github.com/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api/branch/main/graph/badge.svg)](https://codecov.io/gh/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api)
[![Commit activity](https://img.shields.io/github/commit-activity/m/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api)](https://img.shields.io/github/commit-activity/m/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api)
[![License](https://img.shields.io/github/license/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api)](https://img.shields.io/github/license/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api)

this is the backend API for the skillforge project to provide the students with one-to-one learning tutor help

- **Github repository**: <https://github.com/https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api/>
- **Documentation** <https://https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools.github.io/skillforge-api/>

## Getting started with your project

### 1. Create a New Repository

First, create a repository on GitHub with the same name as this project, and then run the following commands:

```bash
git init -b main
git add .
git commit -m "init commit"
git remote add origin git@github.com:https://studi-ai@dev.azure.com/studi-ai/Skillforge/_git/ai-commun-tools/skillforge-api.git
git push -u origin main
```

### 2. Set Up Your Development Environment

First, create a `.env` file from the template:

```bash
cp .env.sample .env
```

then edit the AICOMMONTOOLS_LOCAL_PATH variable to point to the AICommonTools repository on your local machine.

Then, install the environment and the pre-commit hooks with

```bash
make install
```

That will also generate your `uv.lock` file

### 3. Run the pre-commit hooks

Initially, the CI/CD pipeline might be failing due to formatting issues. To resolve those run:

```bash
uv run pre-commit run -a
```
### 4. Install the database
To be able to run the API locally, you'll also need to setup the Postgres database server on your local machine.
If you're on windows, you can download it from <https://www.postgresql.org/download/windows/>, then run the setup.

You'll be asked to setup the superuser password. To match the default value in the ".env" file, you can set it to "admin", else you can chosse you prefered password, then change the value of POSTGRES_PASSWORD in the ".env" file.

After that, you'll need to create the database. To do so, you can, from pgAdmin, run this query:
```sql
CREATE DATABASE skillforge_dev
    WITH
    OWNER = postgres
    ENCODING = 'UTF8'
    LC_COLLATE = 'fr-FR'
    LC_CTYPE = 'fr-FR'
    LOCALE_PROVIDER = 'libc'
    TABLESPACE = pg_default
    CONNECTION LIMIT = -1
    IS_TEMPLATE = False;
```

Once the database created, the tables will be created and static data inserted automatically when you run the API for the first time. You also have endpoints available from the "admin" router to handle database operations.

### 5. Commit the changes

Lastly, commit the changes made by the two steps above to your repository.

```bash
git add .
git commit -m 'Fix formatting issues'
git push origin main
```

You are now ready to start development on your project!
The CI/CD pipeline will be triggered when you open a pull request, merge to main, or when you create a new release.

To finalize the set-up for publishing to PyPI, see [here](https://fpgmaas.github.io/cookiecutter-uv/features/publishing/#set-up-for-pypi).
For activating the automatic documentation with MkDocs, see [here](https://fpgmaas.github.io/cookiecutter-uv/features/mkdocs/#enabling-the-documentation-on-github).
To enable the code coverage reports, see [here](https://fpgmaas.github.io/cookiecutter-uv/features/codecov/).

## Releasing a new version



---

Repository initiated with [fpgmaas/cookiecutter-uv](https://github.com/fpgmaas/cookiecutter-uv).
