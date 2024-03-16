using System.Text.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;

public class ThreadService : IDisposable
{
    public const string threadPath = "..\\outputs\\";
    public const string endMoeTag = "[FIN_MOE_ASSIST]";
    private DateTime? latestFileModification = null;
    private Timer? checkFileTimer;
    private ThreadModel? messages = null;
    public event Action OnFileChanged;

    public ThreadService()
    {
        InitializeFileWatcher();
    }

    public ThreadModel GetMoeMoaExchange()
    {
        //if (messages is not null)
        //    return messages;

        var jsonFilePath = Path.Combine(threadPath, "MOA_MOE_exchanges.json");
        if (!File.Exists(jsonFilePath))
            return new ThreadModel();

        var jsonData = File.ReadAllText(jsonFilePath);
        messages = JsonSerializer.Deserialize<ThreadModel>(jsonData);

        // Change end message of MOE & make it editable by user
        if (messages != null && messages.Any())
        {
            if (messages!.Last().Content.Contains(endMoeTag))
            {
                messages![messages.Count - 1] = messages!.Last() with { Content = "Merci. Je n'ai plus d'autres questions. Avez-vous d'autres points à aborder ? Sinon, cliquez sur 'Suivant'" };
                messages.Add(new MessageModel("MOA", "Ajouter des points à aborder avec le MOE si vous le souhaitez", 0));
            }

            if (!messages!.Last().IsSender)
                messages?.Last().SetAsLastThreadMessage();
        }


        return messages ?? new ThreadModel();
    }

    public void AddNewMessage(MessageModel newMessage)
    {
        if (messages is null)
            messages = new ThreadModel();
        messages.Add(newMessage);
    }

    public void InitializeFileWatcher()
    {
        var jsonFilePath = Path.Combine(threadPath, "MOA_MOE_exchanges.json");
        var fileInfo = new FileInfo(jsonFilePath);
        latestFileModification = fileInfo?.LastWriteTime;

        // Timer setup - checks every second (1000 milliseconds)
        checkFileTimer = new Timer(CheckFileForChanges, jsonFilePath, 0, 1000);
    }

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
            OnFileChanged?.Invoke();
            return;
        }

        // Check if the file has been modified or created since the last check
        if (fileInfo.LastWriteTime > (latestFileModification ?? DateTime.MinValue) 
            || fileInfo.CreationTime > (latestFileModification ?? DateTime.MinValue))
        {
            latestFileModification = fileInfo.LastWriteTime > fileInfo.CreationTime ? fileInfo.LastWriteTime : fileInfo.CreationTime;
            OnFileChanged?.Invoke();
        }
    }

    //public void OnFileChanged()
    //{
    //    GetMoeMoaExchange();

    //    // Trigger a UI refresh if necessary. For Blazor Server, consider using the CircuitHandler.
    //    // For simplicity, force reloading the current page might not be the most efficient way.
    //    // _navigationManager.NavigateTo(_navigationManager.Uri, forceLoad: true);
    //}

    public void Dispose()
    {
        checkFileTimer?.Dispose();
    }
}
