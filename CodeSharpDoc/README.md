<img src="file:///./CodeSharpDoc-logo.png" title="" alt="logo" data-align="center">

<H2>Welcome to CodeSharpDoc</H2>


*This tool is powered by AI agents (and the LLM of your choice)
It's capable of automatic generation of methods summaries for a whole C# projects in a single run!*

Enjoy!



<H4>How to install?**</H4>



Into a Git bash terminal (ctrl+shift+ù - in VS Code on Windows):

- Create the python environment (here it's named '`senv`' but it can be set to you own name, or use `conda`):
  `python -m venv senv`

- Activate the environment:
  `senv/Scripts/activate`

- Download the required packages (you might need to run VS Code as administrator)
  `pip install -r requirements.txt`

<u>WARNING</u>: to reinstall 'pip' on venv whether pip don't work anymore, do:
`python -m ensurepip --upgrade
python -m pip install --upgrade pip`
then do: `Get-Command pip` and check the 'source' column value

To update all your libs, do: `pip install --upgrade -r requirements.txt`
*(you can also create file with the updated list of used libs doing: pip freeze > requirements.g.txt)