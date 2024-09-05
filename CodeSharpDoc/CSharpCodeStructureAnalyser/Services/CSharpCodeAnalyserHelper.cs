using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis;

namespace CSharpCodeStructureAnalyser.Services;

public static class CSharpCodeAnalyserHelper
{
    public static string GetSummary(SyntaxNode decl)
    {
        var trivia = decl.GetLeadingTrivia()
                         .Select(t => t.GetStructure())
                         .OfType<DocumentationCommentTriviaSyntax>()
                         .FirstOrDefault();

        if (trivia == null) return string.Empty;

        var summaryNode = trivia.ChildNodes()
                                .OfType<XmlElementSyntax>()
                                .FirstOrDefault(e => e.StartTag.Name.LocalName.Text == "summary");

        if (summaryNode == null) return string.Empty;

        var summaryText = summaryNode.Content
                                     .OfType<XmlTextSyntax>()
                                     .Select(t => t.ToFullString())
                                     .Where(line => !string.IsNullOrWhiteSpace(line))
                                     .Aggregate(string.Empty, (current, next) => current + next.Trim() + " ");
        
        var lines = summaryText.Split(new[] { "\r\n", "\n" }, StringSplitOptions.None);
        var processedLines = lines.Select(line => line.Contains("///") ? line.Substring(line.IndexOf("///") + 3).Trim() : line.Trim());
        var cleanedSummary = string.Join("\r\n", processedLines).Trim();
        return cleanedSummary;
    }
}
