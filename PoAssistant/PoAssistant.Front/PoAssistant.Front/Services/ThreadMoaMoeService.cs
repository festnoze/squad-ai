using System.Text.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;

public class ThreadMoaMoeService : IDisposable
{
    private ThreadModel? messages = null;
    public event Action? OnThreadChanged = null;
    private bool isWaitingForLLM = false;
    public const string endMoeTag = "[FIN_MOE_ASSIST]";

    public ThreadMoaMoeService()
    {
        //InitializeFileWatcher();
    }

    public const string defaultIntroMessage = "Cliquez sur le stylo à droite pour commencer";
    public ThreadModel GetMoeMoaThread()
    {
        if (messages is null)
        {
            messages = new ThreadModel("MOA", defaultIntroMessage, true);
            isWaitingForLLM = false;
        }
        return messages!;
    }

    public void AddNewMessage(MessageModel newMessage)
    {
        if (messages is null)
            messages = new ThreadModel();

        messages.Add(newMessage);
        CheckNeedToModifyLastMessage();

        OnThreadChanged?.Invoke();
    }

    public void DeleteMoaMoeThread()
    {
        messages = null;
        isWaitingForLLM = true;
    }

    private void CheckNeedToModifyLastMessage()
    {
        // Change end message of MOE & make it editable by user
        if (messages != null && messages.Any())
        {
            if (messages!.Last().Source == "MOE" &&(messages!.Last().Content.Contains(endMoeTag) || messages!.Last().Content.StartsWith("Merci")))
            {
                messages!.Last().ChangeContent("Merci. Nous avons fini, j'ai tous les éléments dont j'ai besoin. Avez-vous d'autres points à aborder ?");
                messages.Add(new MessageModel("MOA", "Ajouter des points à aborder avec le MOE si vous le souhaitez. Sinon, cliquez 'Envoyer' pour passez à l'étape de rédaction de l'US", 0));
                isWaitingForLLM = false;
            }

            messages!.RemoveLastThreadMessageFlags();

            if (!messages!.Last().IsSender)
                messages?.Last().SetAsLastThreadMessage();
        }
    }

    public bool IsLoading()
    {
        return isWaitingForLLM;
    }

    public void EditingLastMessage()
    {
        if (messages != null && messages.Count() == 1 && !messages!.Last().IsSavedMessage)
            messages!.Last().ChangeContent(string.Empty);
    }

    public void SavedUserMessage()
    {
        var needFilePath = "..\\..\\need.txt";
        if (messages != null && messages.Count() == 1)
        {
            messages!.Last().IsSavedMessage = true;
            File.WriteAllText(needFilePath, messages!.Single().Content);
        }
    }

    public void Dispose()
    {}
}
