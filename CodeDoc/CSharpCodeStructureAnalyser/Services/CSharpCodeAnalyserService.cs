﻿using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

using CSharpCodeStructureAnalyser.Models;

namespace CSharpCodeStructureAnalyser.Services;

public static class CSharpCodeAnalyserService
{

    public static List<StructureDesc> AnalyzeFiles(List<string> filesPath, bool doesMethodsShiftIndexesIncludeActualSummaries)
    {
        var csFilesCode = CodeLoaderService.LoadCsFiles(filesPath);
        var structures = new List<StructureDesc>();

        foreach (var file in csFilesCode)
        {
            var structsWithSummaries = AnalyzeFile(file.Value, file.Key, false);

            List<StructureDesc> structsWithoutSummaries = null!;
            if (!doesMethodsShiftIndexesIncludeActualSummaries)
            {
                structsWithoutSummaries = AnalyzeFile(file.Value, file.Key, true);
                CopyExistingSummariesToStructs(ref structsWithoutSummaries, ref structsWithSummaries);
            }

            structures.AddRange(doesMethodsShiftIndexesIncludeActualSummaries ? structsWithSummaries : structsWithoutSummaries);
        }

        return structures;
    }

    private static void CopyExistingSummariesToStructs(ref List<StructureDesc> targetStructs, ref List<StructureDesc> structsWithSummaries)
    {
        foreach (var structWithSummaries in structsWithSummaries)
        {
            var targetStruct = targetStructs.Single(s => s.Name == structWithSummaries.Name);
            foreach (var method in structWithSummaries.Methods)
            {
                var targetMethod = targetStruct.Methods.First(m => 
                    m.Name == method.Name && 
                    m.AccessModifier == method.AccessModifier && 
                    m.Params.Count == method.Params.Count && 
                    m.Params.All(p => method.Params.Any(mp => mp.Name == p.Name && mp.ParamType == p.ParamType)));

                targetMethod.ExistingSummary = method.ExistingSummary;
            }
            targetStruct.ExistingSummary = structWithSummaries.ExistingSummary;
        }
    }

    public static List<StructureDesc> AnalyzeFile(string fileCode, string filePath, bool removeSummaries = true)
    {
        // Remove existing summaries first
        var codeWoSummaries = string.Empty;
        if (removeSummaries)
            codeWoSummaries = CodeEditionService.RemoveExistingSummariesFromFile(fileCode);
        else
            codeWoSummaries = fileCode;

        var tree = CSharpSyntaxTree.ParseText(codeWoSummaries);
        var structures = new List<StructureDesc>();

        foreach (var syntaxNode in tree.GetCompilationUnitRoot().DescendantNodes())
        {
            var structType = GetStructType(syntaxNode);
            if (structType != null)
            {
                var structure = CreateStructureDesc(syntaxNode, filePath, structType!.Value);

                //Shift indexes of containing structures having embedded structures
                if (structures.Any(str => str.IndexShiftCode < structure.IndexShiftCode && str.EndCodeIndex > structure.EndCodeIndex))
                {
                    var structsWithEmbededOnes = structures.Where(str => str.IndexShiftCode < structure.IndexShiftCode && str.EndCodeIndex > structure.IndexShiftCode).ToList();
                    structsWithEmbededOnes.ForEach(s => s.IndexShiftCode += structure.EndCodeIndex - structure.IndexShiftCode);
                }
                structures.Add(structure);
            }
        }
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

    private static StructureType? GetStructType(SyntaxNode syntaxNode)
    {
        StructureType? structType;
        if (syntaxNode is ClassDeclarationSyntax)
            structType = StructureType.Class;
        else if (syntaxNode is InterfaceDeclarationSyntax)
            structType = StructureType.Interface;
        else if (syntaxNode is EnumDeclarationSyntax)
            structType = StructureType.Enum;
        else if (syntaxNode is RecordDeclarationSyntax)
            structType = StructureType.Record;
        else
            structType = null;
        return structType;
    }

    private static StructureDesc CreateStructureDesc(SyntaxNode syntaxNode, string filePath, StructureType structType)
    {
        var namespaceName = syntaxNode.Ancestors().OfType<NamespaceDeclarationSyntax>().FirstOrDefault()?.Name.ToString();
        if (namespaceName is null)
            namespaceName = syntaxNode.Ancestors().OfType<FileScopedNamespaceDeclarationSyntax>().FirstOrDefault()?.Name.ToString();
        if (namespaceName is null)
            namespaceName = "GlobalNamespaceOrNoNamespace";
        var usings = syntaxNode.SyntaxTree.GetCompilationUnitRoot().Usings.Select(u => u.Name!.ToString()).ToList();
        var structName = syntaxNode.ChildTokens().FirstOrDefault(t => t.IsKind(SyntaxKind.IdentifierToken)).ValueText;
        var accessModifier = GetAccessModifiers(syntaxNode);
        var attributes = GetAttributes(syntaxNode);

        var baseClassName = string.Empty;
        var interfacesNames = new List<string>();
        var methods = new List<MethodDesc>();
        var properties = new List<PropertyDesc>();
        EnumMembersDesc? enumMembers = null;

        if (syntaxNode is ClassDeclarationSyntax classDecl)
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
        else if (syntaxNode is RecordDeclarationSyntax recordDecl)
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
        else if (syntaxNode is InterfaceDeclarationSyntax interfaceDecl)
        {
            interfacesNames = interfaceDecl.BaseList?.Types.Select(t => t.ToString()).ToList() ?? new List<string>();
            methods = interfaceDecl.Members.OfType<MethodDeclarationSyntax>().Select(m => MethodDesc.CreateMethodDescFromSyntax(m)).ToList();
            properties = interfaceDecl.Members.OfType<PropertyDeclarationSyntax>().Select(p => PropertyDesc.GetPropertyDescFromSynthax(p)).ToList();
        }
        else if (syntaxNode is EnumDeclarationSyntax enumDecl)
        {
            // Enums do not have methods
            // Enums do not have properties

            int nextValue = 0;
            enumMembers = new EnumMembersDesc();
            foreach (var member in enumDecl.Members.OfType<EnumMemberDeclarationSyntax>())
            {
                int value;
                if (member.EqualsValue != null && int.TryParse(member.EqualsValue.Value.ToString(), out value))
                {
                    nextValue = value;
                }
                enumMembers.Members.Add(new EnumMemberDesc(member.Identifier.Text, nextValue));
                nextValue++;
            }
        }

        var existingSummary = CSharpCodeAnalyserHelper.GetSummary(syntaxNode);
        var indentLevel = syntaxNode.GetLeadingTrivia().ToString().Split('\n').Last().Count(c => c == ' ') / 4;
        
        // Find the actual start index of the class excluding preprocessor directives
        var leadingTrivia = syntaxNode.GetLeadingTrivia();
        var startIndex = syntaxNode.FullSpan.Start;
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
                    startIndex = trivia.FullSpan.End;
        }

        var endIndex = syntaxNode.FullSpan.End;//syntaxNode.SyntaxTree.GetLineSpan(syntaxNode.FullSpan).EndLinePosition.Line + 1;


        return new StructureDesc(
            filePath,
            startIndex,
            endIndex,
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
            properties,
            enumMembers
        );
    }

    private static string GetAccessModifiers(SyntaxNode syntaxNode)
    {
        if (syntaxNode is BaseTypeDeclarationSyntax baseTypeDecl)
        {
            return baseTypeDecl.Modifiers.ToString();
        }
        else if (syntaxNode is EnumDeclarationSyntax enumDecl)
        {
            return enumDecl.Modifiers.ToString();
        }
        else if (syntaxNode is RecordDeclarationSyntax recordDecl)
        {
            return recordDecl.Modifiers.ToString();
        }
        return string.Empty;
    }
    private static List<string> GetAttributes(SyntaxNode syntaxNode)
    {
        return syntaxNode.ChildNodes()
                   .OfType<AttributeListSyntax>()
                   .SelectMany(a => a.Attributes)
                   .Select(a => a.ToString())
                   .ToList();
    }
}