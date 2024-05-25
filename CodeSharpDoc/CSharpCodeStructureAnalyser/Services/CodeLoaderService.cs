using System;
using System.Collections.Generic;
using System.IO;

namespace CSharpCodeStructureAnalyser.Services;

public static class CodeLoaderService
{
    public static List<KeyValuePair<string, string>> LoadCsFiles(string folderPath)
    {
        List<KeyValuePair<string, string>> csFilesCode = new List<KeyValuePair<string, string>>();
        var files = GetCsFiles(folderPath);
        foreach (var filePath in files)
            csFilesCode.Add(new KeyValuePair<string, string>(filePath, LoadFile(filePath)));
        
        return csFilesCode;
    }

    public static List<string> GetCsFiles(string rootDirectory)
    {
        List<string> csFiles = new List<string>();
        foreach (var file in Directory.GetFiles(rootDirectory, "*.cs", SearchOption.AllDirectories))
        {
            csFiles.Add(file.Replace("\\", "/"));
        }
        return csFiles;
    }

    public static string LoadFile(string filePath)
    {
        return File.ReadAllText(filePath);
    }

}

