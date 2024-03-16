namespace PoAssistant.Front.Services;

public class FileWatcherService : IDisposable
{
    private Timer? _checkFileTimer;
    private DateTime _lastFileCheckTime;
    private readonly string _jsonFilePath = Path.Combine("YourDirectory", "MOA_MOE_exchanges.json");
    public event Action OnFileChanged;

    public FileWatcherService()
    {
        InitializeFileWatcher();
    }

    private void InitializeFileWatcher()
    {
        var fileInfo = new FileInfo(_jsonFilePath);
        _lastFileCheckTime = fileInfo.LastWriteTime;
        _checkFileTimer = new Timer(CheckFileForChanges, null, 0, 1000);
    }

    private void CheckFileForChanges(object? state)
    {
        var fileInfo = new FileInfo(_jsonFilePath);
        if (fileInfo.LastWriteTime > _lastFileCheckTime)
        {
            _lastFileCheckTime = fileInfo.LastWriteTime;
            OnFileChanged?.Invoke();
        }
    }

    public void Dispose()
    {
        _checkFileTimer?.Dispose();
    }
}

