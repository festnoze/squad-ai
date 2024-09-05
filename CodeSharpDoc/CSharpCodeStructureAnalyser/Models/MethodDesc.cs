using System.Text.RegularExpressions;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis;
using System.Text.Json.Serialization;
using Newtonsoft.Json;
using CSharpCodeStructureAnalyser.Services;

namespace CSharpCodeStructureAnalyser.Models;

public record MethodDesc : BaseDesc
{
    [JsonPropertyName("code_start_index")]
    public int CodeStartIndex { get; set; }

    [JsonPropertyName("existing_summary")]
    public string ExistingSummary { get; set; }

    [JsonPropertyName("access_modifier")]
    public string AccessModifier { get; set; }

    [JsonPropertyName("attributs")]
    public List<string> Attributes { get; set; }

    [JsonPropertyName("method_name")]
    public string MethodName { get; set; }

    [JsonPropertyName("method_return_type")]
    public string ReturnType { get; set; }

    [JsonPropertyName("params")]
    public List<ParameterDesc> Params { get; set; }

    [JsonPropertyName("indent_level")]
    public int IndentLevel { get; set; }

    [JsonPropertyName("code")]
    public string Code { get; set; }

    [JsonPropertyName("is_async")]
    public bool IsAsync { get; set; }

    [JsonPropertyName("is_task")]
    public bool IsTask { get; set; }

    [JsonPropertyName("is_ctor")]
    public bool IsCtor { get; set; }

    [JsonPropertyName("is_static")]
    public bool IsStatic { get; set; }

    [JsonPropertyName("is_abstract")]
    public bool IsAbstract { get; set; }

    [JsonPropertyName("is_override")]
    public bool IsOverride { get; set; }

    [JsonPropertyName("is_virtual")]
    public bool IsVirtual { get; set; }

    [JsonPropertyName("is_sealed")]
    public bool IsSealed { get; set; }

    [JsonPropertyName("is_new")]
    public bool IsNew { get; set; }

    [JsonPropertyName("code_chunks")]
    public List<string> CodeChunks { get; set; }

    [JsonPropertyName("generated_xml_summary")]
    public string GeneratedXmlSummary { get; set; }

    [JsonPropertyName("summary")]
    public string Summary { get; set; }


    public MethodDesc(
        int codeStartIndex,
        string existingSummary,
        string accessModifier,
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
        AccessModifier = accessModifier;
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
        CodeChunks = new List<string>();
    }


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

    public string GetMethodSignature(bool withParams = false)
    {
        var methodSignature = $"{AccessModifier}";
        
        if (IsAsync) methodSignature += " async";
        if (IsOverride) methodSignature += " override";
        if (IsVirtual) methodSignature += " virtual";
        if (IsSealed) methodSignature += " sealed";
        if (IsNew) methodSignature += " new";

        methodSignature += $" {ReturnType} {MethodName}(";

        if (withParams)
        {
            methodSignature += string.Join(", ", Params);
            methodSignature += ")";
        }
        return methodSignature;
    }

    public string GetMethodSignatureStart()
    {
        return $"{AccessModifier} {ReturnType} {MethodName}(".Trim();
    }

    private string Indent(int level)
    {
        return new string(' ', level * 4);
    }

    public static MethodDesc CreateMethodDescFromSyntax(MethodDeclarationSyntax method)
    {
        var paramList = method.ParameterList.Parameters.Select(p => new ParameterDesc(
            p.Identifier.Text,
            p.Type!.ToString(),
            p.Default != null,
            p.Default?.Value.ToString() ?? string.Empty,
            null,
            null
        )).ToList();

        // detect the indentation level of the method 
        var indentLevel = method.GetLeadingTrivia().ToString().Split("\r\n").Last().Count(c => c == ' ')/4;
        var accessModifier = method.Modifiers.FirstOrDefault(m => m.IsKind(SyntaxKind.PublicKeyword) || m.IsKind(SyntaxKind.ProtectedKeyword) || m.IsKind(SyntaxKind.PrivateKeyword) || m.IsKind(SyntaxKind.InternalKeyword)).ToString() ?? SyntaxKind.PrivateKeyword.ToString();

        // Find the actual start index of the method excluding preprocessor directives
        var leadingTrivia = method.GetLeadingTrivia();
        var methodStartIndex = method.FullSpan.Start;
        foreach (var trivia in leadingTrivia.ToList())
        {
            if (trivia.IsKind(SyntaxKind.RegionDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.EndRegionDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.IfDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.EndIfDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.ElseDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.ElifDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.DefineDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.UndefDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.PragmaWarningDirectiveTrivia) ||
                trivia.IsKind(SyntaxKind.PragmaChecksumDirectiveTrivia))
                    methodStartIndex = trivia.FullSpan.End;
        }

        return new MethodDesc(
            methodStartIndex,
            CSharpCodeAnalyserHelper.GetSummary(method),
            accessModifier,
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

    public string ToJson()
    {
        return JsonConvert.SerializeObject(this, Formatting.Indented);
    }
}