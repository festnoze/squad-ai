using System;
using System.Collections.Generic;
using System.IO;

namespace CSharpCodeStructureAnalyser.Services;

public static class CodeLoaderService
{
    public static List<KeyValuePair<string, string>> LoadCsFolderFiles(string folderPath)
    {
        var files = GetCsFiles(folderPath);
        return LoadCsFiles(files);
    }

    public static List<KeyValuePair<string, string>> LoadCsFiles(List<string> filesPath)
    {
        List<KeyValuePair<string, string>> csFilesCode = new List<KeyValuePair<string, string>>();
        foreach (var filePath in filesPath)
        {
            csFilesCode.Add(new KeyValuePair<string, string>(filePath, LoadFile(filePath)));
        }
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

