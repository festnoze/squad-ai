using PoAssistant.Front.Data;
using System.Text.Json;

namespace PoAssistant.Front.Services;

public class FileWatcherService : IDisposable
{
    private Timer? _checkFileTimer;
    private DateTime _lastFileCheckTime;
    private readonly string _jsonFilePath = Path.Combine("YourDirectory", "MOA_MOE_exchanges.json");
    private DateTime? latestFileModification = null;
    private Timer? checkFileTimer;
    private ThreadModel? messages = null;
    public const string threadPath = "..\\outputs\\";
    public event Action? OnThreadChanged = null;

    public FileWatcherService()
    {
        InitializeFileWatcher();
    }


    // Obsolete: Load the json file containing the exchange MOE/MOA
    public ThreadModel LoadMoeMoaExchangeFromFile()
    {
        //if (messages is not null)
        //    return messages;

        var jsonFilePath = Path.Combine(threadPath, "MOA_MOE_exchanges.json");
        if (!File.Exists(jsonFilePath))
            return new ThreadModel();

        var jsonData = File.ReadAllText(jsonFilePath);
        messages = JsonSerializer.Deserialize<ThreadModel>(jsonData);
       // CheckNeedToModifyLastMessage();

        return messages ?? new ThreadModel();
    }


    // Obsolete: timer which regularly check for json file changes
    public void InitializeFileWatcher()
    {
        var jsonFilePath = Path.Combine(threadPath, "MOA_MOE_exchanges.json");
        var fileInfo = new FileInfo(jsonFilePath);
        latestFileModification = fileInfo?.LastWriteTime;

        // Timer setup - checks every second (1000 milliseconds)
        checkFileTimer = new Timer(CheckFileForChanges, jsonFilePath, 0, 1000);
    }

    // Obsolete: used to check if json file has changed
    private void CheckFileForChanges(object? state)
    {
        var jsonFilePath = state as string;
        if (string.IsNullOrEmpty(jsonFilePath))
            return;

        var fileInfo = new FileInfo(jsonFilePath);

        if (!fileInfo.Exists)
        {
            if (latestFileModification is null)
                return;

            latestFileModification = null;
            OnThreadChanged?.Invoke();
            return;
        }

        // Check if the file has been modified or created since the last check
        if (fileInfo.LastWriteTime > (latestFileModification ?? DateTime.MinValue)
            || fileInfo.CreationTime > (latestFileModification ?? DateTime.MinValue))
        {
            latestFileModification = fileInfo.LastWriteTime > fileInfo.CreationTime ? fileInfo.LastWriteTime : fileInfo.CreationTime;
            OnThreadChanged?.Invoke();
        }
    }

    public void Dispose()
    {
        _checkFileTimer?.Dispose();
    }
}

