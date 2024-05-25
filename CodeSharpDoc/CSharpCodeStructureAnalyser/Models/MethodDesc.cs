using System.Text.RegularExpressions;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.CSharp;
using Newtonsoft.Json;
using Microsoft.CodeAnalysis;

namespace CSharpCodeStructureAnalyser.Models;

public record MethodDesc : BaseDesc
{
    public int CodeStartIndex { get; set; }
    public string ExistingSummary { get; set; }
    public List<string> Attributes { get; set; }
    public string ReturnType { get; set; }
    public List<ParameterDesc> Params { get; set; }
    public int IndentLevel { get; set; }
    public string Code { get; set; }
    public bool IsAsync { get; set; }
    public bool IsTask { get; set; }
    public bool IsCtor { get; set; }
    public bool IsStatic { get; set; }
    public bool IsAbstract { get; set; }
    public bool IsOverride { get; set; }
    public bool IsVirtual { get; set; }
    public bool IsSealed { get; set; }
    public bool IsNew { get; set; }

    private List<string> _codeChunks;
    public string GeneratedXmlSummary { get; set; }
    public string Summary { get; set; }
    public string MethodName { get; set; }

    public MethodDesc(
        int codeStartIndex,
        string existingSummary,
        List<string> attributes,
        string methodName,
        string methodReturnType,
        List<ParameterDesc> methodParams,
        int indentLevel,
        string code,
        bool isAsync = false,
        bool isTask = false,
        bool isCtor = false,
        bool isStatic = false,
        bool isAbstract = false,
        bool isOverride = false,
        bool isVirtual = false,
        bool isSealed = false,
        bool isNew = false)
        : base(methodName)
    {
        CodeStartIndex = codeStartIndex;
        ExistingSummary = existingSummary;
        Attributes = attributes;
        MethodName = methodName;
        ReturnType = methodReturnType;
        Params = methodParams;
        IndentLevel = indentLevel;
        Code = code;
        IsAsync = isAsync;
        IsTask = isTask;
        IsCtor = isCtor;
        IsStatic = isStatic;
        IsAbstract = isAbstract;
        IsOverride = isOverride;
        IsVirtual = isVirtual;
        IsSealed = isSealed;
        IsNew = isNew;
        _codeChunks = null;
    }

    public List<string> CodeChunks => _codeChunks ?? new List<string> { Code };

    public string ToCode(int indentLevel = 1, bool includeSummary = false)
    {
        var methodCode = string.Empty;

        if (includeSummary)
        {
            if (!string.IsNullOrEmpty(GeneratedXmlSummary))
            {
                methodCode += $"{Indent(indentLevel)}{GeneratedXmlSummary}\n";
            }
            else
            {
                methodCode += $"{Indent(indentLevel)}{Summary}\n";
            }
        }

        methodCode += $"{Indent(indentLevel)}{ReturnType} {MethodName}({string.Join(", ", Params)})\n";
        methodCode += $"{Indent(indentLevel)}{{\n";
        indentLevel++;
        methodCode += $"{Indent(indentLevel)}{Code}\n";
        indentLevel--;
        methodCode += $"{Indent(indentLevel)}}}\n\n";
        return methodCode;
    }

    private string Indent(int level)
    {
        return new string(' ', level * 4);
    }

    public static MethodDesc CreateMethodDescFromSyntax(MethodDeclarationSyntax method)
    {
        var paramList = method.ParameterList.Parameters.Select(p => new ParameterDesc(
            p.Identifier.Text,
            p.Type.ToString(),
            p.Default != null,
            p.Default?.Value.ToString()
        )).ToList();

        // detect the indentation level of the method 
        var indentLevel = method.GetLeadingTrivia().ToString().Split('\n').Last().Count(c => c == ' ')/4;

        return new MethodDesc(
            method.FullSpan.Start,
            method.GetLeadingTrivia().ToString(),
            method.AttributeLists.SelectMany(a => a.Attributes).Select(a => a.ToString()).ToList(),
            method.Identifier.Text,
            method.ReturnType.ToString(),
            paramList,
            indentLevel,
            method.Body?.ToString() ?? method.ExpressionBody?.Expression.ToString() ?? string.Empty,
            method.Modifiers.Any(m => m.IsKind(SyntaxKind.AsyncKeyword)),
            method.ReturnType.ToString().Contains("Task"),
            false,
            method.Modifiers.Any(m => m.IsKind(SyntaxKind.StaticKeyword)),
            method.Modifiers.Any(m => m.IsKind(SyntaxKind.AbstractKeyword)),
            method.Modifiers.Any(m => m.IsKind(SyntaxKind.OverrideKeyword)),
            method.Modifiers.Any(m => m.IsKind(SyntaxKind.VirtualKeyword)),
            method.Modifiers.Any(m => m.IsKind(SyntaxKind.SealedKeyword)),
            method.Modifiers.Any(m => m.IsKind(SyntaxKind.NewKeyword))
        );
    }

    private static List<ParameterDesc> GetMethodParameters(string methodSign)
    {
        var paramsStartIndex = methodSign.IndexOf('(') + 1;
        var paramsEndIndex = methodSign.LastIndexOf(')');
        var paramsStr = methodSign.Substring(paramsStartIndex, paramsEndIndex - paramsStartIndex);
        var paramsList = paramsStr.Split(',').Select(param => param.Trim()).Where(param => !string.IsNullOrEmpty(param)).ToList();
        var paramsDesc = paramsList.Select(param => ParameterDesc.FactoryParamDescFromCode(param)).ToList();
        return paramsDesc;
    }

    private static List<string> DetectAttributes(string code)
    {
        var attributes = new List<string>();
        var attributePattern = @"\[\s*(.*?)\s*\]";
        var lines = code.Split('\n');
        foreach (var line in lines)
        {
            var matches = Regex.Matches(line, attributePattern);
            foreach (Match match in matches)
            {
                attributes.Add(match.Value);
            }
        }
        return attributes;
    }

    public string ToJson()
    {
        return JsonConvert.SerializeObject(this, Formatting.Indented);
    }
}