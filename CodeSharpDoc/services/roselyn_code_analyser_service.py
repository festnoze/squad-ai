# # from pythonnet import load
# # load("coreclr")

# import clr
# clr.AddReference("System")
# clr.AddReference("System.IO")
# clr.AddReference("Microsoft.CodeAnalysis")
# clr.AddReference("Microsoft.CodeAnalysis.CSharp")

# from System.IO import File
# from Microsoft.CodeAnalysis import SyntaxTree
# from Microsoft.CodeAnalysis.CSharp import CSharpSyntaxTree
# from Microsoft.CodeAnalysis.CSharp.Syntax import ClassDeclarationSyntax, MethodDeclarationSyntax, AttributeListSyntax

# def get_method_start_line(tree, method):
#     # Get the line position of the method declaration
#     line_span = tree.GetLineSpan(method.Span)
#     return line_span.StartLinePosition.Line + 1  # +1 because lines are zero-indexed

# def get_line_before_attributes(tree, method):
#     # Check if there are any attributes
#     if method.AttributeLists.Count > 0:
#         # Get the line position of the first attribute
#         first_attribute = method.AttributeLists.First()
#         line_span = tree.GetLineSpan(first_attribute.Span)
#         return line_span.StartLinePosition.Line  # Line before the first attribute
#     else:
#         # No attributs, return the method start line
#         return get_method_start_line(tree, method)

# # Read the C# file
# code = File.ReadAllText("YourFile.cs")
# tree = CSharpSyntaxTree.ParseText(code)
# root = tree.GetCompilationUnitRoot()

# # Example method name to find
# method_name = "YourMethodName"

# for class_decl in root.DescendantNodes().OfType[ClassDeclarationSyntax]():
#     for method in class_decl.Members.OfType[MethodDeclarationSyntax]():
#         if method.Identifier.Text == method_name:
#             method_start_line = get_method_start_line(tree, method)
#             line_before_attributes = get_line_before_attributes(tree, method)

#             print(f"Method '{method_name}' starts at line: {method_start_line}")
#             print(f"Line before attributes: {line_before_attributes}")
