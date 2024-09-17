<img src="./CodeSharpDoc-logo.png" title="" alt="logo" data-align="center">

<H1 style="text-align: center;">Welcome to CodeSharpDoc</H1>

### What is it?

This tool is about documenting & rewritting your legacy C# code.

### Technicalities

AI powered including: LLM, LangChain, Agents and RAG.

Include: python, langchain, langgraph and C# code.

### Actual features

It's helps you take back control over your (legacy-ish) .NET C# code: 

- *Retro-engeenering*: Automatically generating methods and structures summaries for a whole C# projects with a single click!

- *Documentation*: Create an always up-to-date technical documentations of your C# projects structures & summaries!

- *Querying*: Build a vector database out of your code summaries and relationship. Then ask questions to search your codebase. It helps developers to keep the code factorized, and think DRY: reuse existing methods rather than reinventing the wheel! But even in case of code duplication, it helps you to spot those duplicate implementations when a feature have to be maintained or evolved.

### What comes next ...

- *Unit & functional testing*: Automatically create unit & functionnal tests with dataset appropriate to use cases 

- *Rewrite legacy*: Automatically split your existing legacy code into its functionnal sub-parts with similar abstraction level & reuse of common sub-parts. Also split your legacy code upon responsability to make your code clean and maintainable.  

- Migrate legacy: Automatically translate your old .NET framework or .NET Core 3.1 project into the latest .NET Core with use of the new languages features and nuGets.

<H3>How to install it?</H3>

Into a Git bash terminal (`ctrl+shift+ù` in VS Code, on Windows, with azerty keyboard):

- Create the python virtual environment (hereinafter named '`senv`' but it can be set to you own name. You can rather use `conda`):
  `python -m venv senv`

- Activate the environment:
  `senv/Scripts/activate`

- Download the required packages (you might need to run VS Code as administrator)
  `pip install -r requirements.txt`

- To update all your libs: 
  
  `pip install --upgrade -r requirements.txt`
  *(you can also create file with the updated list of used libs doing: pip freeze > requirements.g.txt)

***Enjoy!***

__

### Troubleshooting

If there's an error on destination folder while doing `pip install` from the `senv `venv, explicitly define the taget directory: 

`pip install --target=C:\Dev\squad-ai\CodeSharpDoc\senv\Lib\site-packages -r requirements.txt`

To reinstall 'pip' on venv if `pip` don't work anymore, do:
`python -m ensurepip --upgrade
python -m pip install --upgrade pip`
then: `Get-Command pip` and check the value of 'source' column