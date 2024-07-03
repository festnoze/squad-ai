using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using System.Collections.Generic;
using System.Linq;

using CSharpCodeStructureAnalyser.Models;

namespace CSharpCodeStructureAnalyser.Services;

public static class CSharpCodeAnalyserService
{
    public static List<StructureDesc> AnalyzeFiles(List<string> filesPath)
    {
        var csFilesCode = CodeLoaderService.LoadCsFiles(filesPath);
        var structures = new List<StructureDesc>();

        foreach (var file in csFilesCode)
        {
            structures.AddRange(AnalyzeFile(file.Value, file.Key));
        }

        return structures;
    }

    public static List<StructureDesc> AnalyzeFile(string fileCode, string filePath)
    {
        //// Remove existing summaries first
        //fileCode = RemoveExistingSummariesFromFile(fileCode);

        var tree = CSharpSyntaxTree.ParseText(fileCode);
        var root = tree.GetCompilationUnitRoot();
        var structures = new List<StructureDesc>();

        foreach (var decl in root.DescendantNodes())
        {
            var structType = GetStructType(decl);
            if (structType != null)
                structures.Add(CreateStructureDesc(decl, fileCode, filePath, structType!.Value));
        }
        //fileCode = AddFakeSummariesToCode(fileCode, structures);
        //File.WriteAllText(filePath, fileCode);

        return structures;
    }

    private static string AddFakeSummariesToCode(string fileCode, List<StructureDesc> structures)
    {
        var summary = $@"
/// <summary>
/// [summaryContent]
/// </summary>";
        var tmp = "";
        for (var i = structures.Count - 1; i >= 0; i--)
        {
            var structure = structures[i];

            for (var j = structure.Methods.Count - 1; j >= 0; j--)
            {
                var method = structure.Methods[j];
                if (method.CodeStartIndex > 0)
                {
                    var methodSummary = summary.Replace("[summaryContent]", method.MethodName);
                    var lines = methodSummary.Split('\n').ToList();
                    for (int k = 0; k < lines.Count; k++)
                    {
                        if (lines[k].Length > 0)
                            lines[k] = new string('\t', method.IndentLevel) + lines[k].Trim();
                    }
                    methodSummary = string.Join('\n', lines);

                    tmp += method.CodeStartIndex.ToString() + ", ";
                    var before = fileCode.Substring(0, method.CodeStartIndex);
                    var after = fileCode.Substring(method.CodeStartIndex);
                    fileCode = before + methodSummary + after;
                }
            }
        }
        return fileCode;
    }

    //public static string RemoveExistingSummariesFromFile(string code)
    //{
    //    var lines = code.Split(new[] { Environment.NewLine }, StringSplitOptions.None);
    //    var filteredLines = lines.Where(line => !line.Trim().StartsWith("///")).ToList();
    //    return string.Join(Environment.NewLine, filteredLines);
    //}

    private static StructureType? GetStructType(SyntaxNode decl)
    {
        StructureType? structType;
        if (decl is ClassDeclarationSyntax)
            structType = StructureType.Class;
        else if (decl is InterfaceDeclarationSyntax)
            structType = StructureType.Interface;
        else if (decl is EnumDeclarationSyntax)
            structType = StructureType.Enum;
        else if (decl is RecordDeclarationSyntax)
            structType = StructureType.Record;
        else
            structType = null;
        return structType;
    }

    private static StructureDesc CreateStructureDesc(SyntaxNode decl, string fullCode, string filePath, StructureType structType)
    {
        var namespaceName = decl.Ancestors().OfType<NamespaceDeclarationSyntax>().FirstOrDefault()?.Name.ToString() ?? string.Empty;
        var usings = decl.SyntaxTree.GetCompilationUnitRoot().Usings.Select(u => u.Name!.ToString()).ToList();
        var structName = decl.ChildTokens().FirstOrDefault(t => t.IsKind(SyntaxKind.IdentifierToken)).ValueText;
        var accessModifier = GetAccessModifiers(decl);
        var attributes = GetAttributes(decl);

        var baseClassName = string.Empty;
        var interfacesNames = new List<string>();
        var methods = new List<MethodDesc>();
        var properties = new List<PropertyDesc>();

        if (decl is ClassDeclarationSyntax classDecl)
        {
            interfacesNames = classDecl.BaseList?.Types.Select(t => t.ToString()).ToList() ?? new List<string>();
            // Determine if inheritance list begins with a base class rather than an interface
            if (interfacesNames.Count > 0 && !interfacesNames[0].StartsWith("I"))
            {
                baseClassName = interfacesNames[0];
                interfacesNames.RemoveAt(0);
            }
            methods = classDecl.Members.OfType<MethodDeclarationSyntax>().Select(m => MethodDesc.CreateMethodDescFromSyntax(m)).ToList();
            properties = classDecl.Members.OfType<PropertyDeclarationSyntax>().Select(p => PropertyDesc.GetPropertyDescFromSynthax(p)).ToList();
        }
        else if (decl is RecordDeclarationSyntax recordDecl)
        {
            interfacesNames = recordDecl.BaseList?.Types.Select(t => t.ToString()).ToList() ?? new List<string>();
            // Determine if inheritance list begins with a base class rather than an interface
            if (interfacesNames.Count > 0 && !interfacesNames[0].StartsWith("I"))
            {
                baseClassName = interfacesNames[0];
                interfacesNames.RemoveAt(0);
            }
            methods = recordDecl.Members.OfType<MethodDeclarationSyntax>().Select(m => MethodDesc.CreateMethodDescFromSyntax(m)).ToList();
            properties = recordDecl.Members.OfType<PropertyDeclarationSyntax>().Select(p => PropertyDesc.GetPropertyDescFromSynthax(p)).ToList();
        }
        else if (decl is InterfaceDeclarationSyntax interfaceDecl)
        {
            interfacesNames = interfaceDecl.BaseList?.Types.Select(t => t.ToString()).ToList() ?? new List<string>();
            methods = interfaceDecl.Members.OfType<MethodDeclarationSyntax>().Select(m => MethodDesc.CreateMethodDescFromSyntax(m)).ToList();
            properties = interfaceDecl.Members.OfType<PropertyDeclarationSyntax>().Select(p => PropertyDesc.GetPropertyDescFromSynthax(p)).ToList();
        }
        else if (decl is EnumDeclarationSyntax)
        {
            // Handle Enum
        }

        var existingSummary = GetSummary(decl);
        var indentLevel = decl.GetLeadingTrivia().ToString().Split('\n').Last().Count(c => c == ' ') / 4;
        var startIndex = decl.FullSpan.Start;

        return new StructureDesc(
            filePath,
            startIndex,
            indentLevel,
            structType,
            namespaceName,
            usings,
            structName,
            accessModifier,
            baseClassName,
            interfacesNames,
            existingSummary,
            attributes,
            methods,
            properties
        );
    }

    private static string GetAccessModifiers(SyntaxNode decl)
    {
        if (decl is BaseTypeDeclarationSyntax baseTypeDecl)
        {
            return baseTypeDecl.Modifiers.ToString();
        }
        else if (decl is EnumDeclarationSyntax enumDecl)
        {
            return enumDecl.Modifiers.ToString();
        }
        else if (decl is RecordDeclarationSyntax recordDecl)
        {
            return recordDecl.Modifiers.ToString();
        }
        return string.Empty;
    }
    private static List<string> GetAttributes(SyntaxNode decl)
    {
        return decl.ChildNodes()
                   .OfType<AttributeListSyntax>()
                   .SelectMany(a => a.Attributes)
                   .Select(a => a.ToString())
                   .ToList();
    }

    private static string GetSummary(SyntaxNode decl)
    {
        var trivia = decl.GetLeadingTrivia()
                          .Select(t => t.GetStructure())
                          .OfType<DocumentationCommentTriviaSyntax>()
                          .FirstOrDefault();

        if (trivia == null)
        {
            return string.Empty;
        }

        var summaryNode = trivia.ChildNodes()
                                 .OfType<XmlElementSyntax>()
                                 .FirstOrDefault(e => e.StartTag.Name.LocalName.Text == "summary");

        return summaryNode?.Content.ToString().Trim() ?? string.Empty;
    }
}