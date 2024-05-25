namespace CSharpCodeStructureAnalyser.Models;

public abstract record BaseDesc
{
    public string Name { get; set; }

    protected BaseDesc(string name)
    {
        Name = name;
    }
}
