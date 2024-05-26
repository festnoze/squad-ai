using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using System.Collections.Generic;
using System.Linq;

using CSharpCodeStructureAnalyser.Models;

namespace CSharpCodeStructureAnalyser.Services;

public static class CSharpCodeAnalyserService
{
    public static List<StructureDesc> AnalyzeFolder(string folderPath)
    {
        var csFilesCode = CodeLoaderService.LoadCsFiles(folderPath);
        var structures = new List<StructureDesc>();

        foreach (var file in csFilesCode)
        {
            structures.AddRange(AnalyzeFile(file.Value, file.Key));
        }

        return structures;
    }

    public static List<StructureDesc> AnalyzeFile(string fileCode, string filePath)
    {
        var tree = CSharpSyntaxTree.ParseText(fileCode);
        var root = tree.GetCompilationUnitRoot();
        var structures = new List<StructureDesc>();

        foreach (var decl in root.DescendantNodes())
        {
            var structType = GetStructType(decl);
            if (structType != null)
                structures.Add(CreateStructureDesc(decl, fileCode, filePath, structType!.Value));
        }

        return structures;
    }

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
        string accessModifier = GetAccessModifiers(decl);

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

        //foreach (var method in methods)
        //{
        //    method.CodeStartIndex = fullCode.IndexOf($"{method.AccessModifier} {method.ReturnType} {method.MethodName}(".Trim());// + method.Params.Join();
        //}

        return new StructureDesc(
            filePath,
            decl.Span.Start,
            structType,
            namespaceName,
            usings,
            structName,
            accessModifier,
            baseClassName,
            interfacesNames,
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
}