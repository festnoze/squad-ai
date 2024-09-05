using Newtonsoft.Json;
using PoAssistant.Front.Data;
using System.Text.RegularExpressions;

namespace PoAssistant.Front.Infrastructure;

public interface IExchangesRepository
{
    List<string> GetAllUserExchangesNames(string username);
    ThreadModel? LoadUserExchange(string username, string exchangeDisplayName, bool truncatedExchangeName = false);
    bool SaveUserExchange(string username, ThreadModel exchange);
}

public class ExchangesRepository : IExchangesRepository
{
    private const string _exchangesDataPath = "savedData\\exchanges\\";

    public ExchangesRepository()
    {
    }

    public List<string> GetAllUserExchangesNames(string username)
    {
        VerifyMainFolderExistance();
        var userExchangeFolderPath = GetUserExchangeFolderPath(username);

        var userExchangesFiles = GetFolderFilesNames(userExchangeFolderPath);

        var userExchangesNames = userExchangesFiles.Select(fileName => ToDisplayName(Path.GetFileNameWithoutExtension(fileName))).ToList();
        return userExchangesNames;
    }

    public ThreadModel? LoadUserExchange(string username, string exchangeDisplayName, bool isTruncatedExchangeName = false)
    {
        if (isTruncatedExchangeName)
        {
            exchangeDisplayName = exchangeDisplayName.Substring(0, exchangeDisplayName.Length - 4);
            var exchangesNames = GetAllUserExchangesNames(username);
            exchangeDisplayName = exchangesNames.First(exchange => exchange.StartsWith(exchangeDisplayName, StringComparison.OrdinalIgnoreCase));
        }

        var userExchangeFolderPath = GetUserExchangeFolderPath(username);

        var exchangePath = userExchangeFolderPath + ToFileSystemName(exchangeDisplayName) + ".json";

        if (!File.Exists(exchangePath))
            return null;

        var exchangeJson = LoadExchangeFromPath(exchangePath);

        return JsonConvert.DeserializeObject<ThreadModel>(exchangeJson);
    }

    public bool SaveUserExchange(string username, ThreadModel exchange)
    {
        var maxTitleLength = 100;
        if (exchange.First().Content.Length < maxTitleLength)
            maxTitleLength = exchange.First().Content.Length;

        var exchangeTitle = ToFileSystemName(exchange.First().Content.Substring(0, maxTitleLength));
        
        var isNewExchange = exchange.Count == 1;
        if (isNewExchange)
            while (DoesExistUserExchangeFile(username, exchangeTitle + ".json"))
                exchangeTitle += "_";

        var exchangePath = GetUserExchangeFolderPath(username) + exchangeTitle + ".json";
        var exchangeJson = JsonConvert.SerializeObject(exchange);

        File.WriteAllText(exchangePath, exchangeJson);
        return isNewExchange;
    }

    private bool DoesExistUserExchangeFile(string username, string exchangeFilePath)
    {
        return File.Exists(GetUserExchangeFolderPath(username) + exchangeFilePath);
    }

    #region private methods

    private string LoadExchangeFromPath(string exchangePath)
    {
        return File.ReadAllText(exchangePath);
    }

    private static void VerifyMainFolderExistance()
    {
        if (!Directory.Exists(_exchangesDataPath))
            Directory.CreateDirectory(_exchangesDataPath);
    }

    private static string GetUserExchangeFolderPath(string username)
    {
        var formatedUsername = ToFileSystemName(username);
        if (!Directory.Exists(_exchangesDataPath + formatedUsername))
            Directory.CreateDirectory(_exchangesDataPath + formatedUsername);

        return _exchangesDataPath + formatedUsername + "\\";
    }

    private List<string> GetFolderFilesNames(string folderPath)
    {
        List<string> fileNames = new List<string>();
        string[] files = Directory.GetFiles(folderPath);
        foreach (string file in files)
        {
            string fileName = Path.GetFileName(file);
            fileNames.Add(fileName);
        }
        return fileNames;
    }

    private static string ToFileSystemName(string username)
    {
        var fileSystemNameWithHandledSpecialChar = username.Replace(",", "__").Replace(".", "_");
        return RemoveSpecialCharacters(fileSystemNameWithHandledSpecialChar);
    }

    private static string ToDisplayName(string username)
    {
        return username.Replace("__", ",").Replace("_", ".");
    }
    public static string RemoveSpecialCharacters(string input)
    {
        var pattern = "[^a-zA-Z0-9_éèêëàâäôöûüçÇîïÏÎÉÈÊËÀÂÄÔÖÛÜ_ -]";
        var replacement = "~";
        Regex regex = new Regex(pattern);
        var result = regex.Replace(input, replacement);
        return result;
    }
    #endregion
}

