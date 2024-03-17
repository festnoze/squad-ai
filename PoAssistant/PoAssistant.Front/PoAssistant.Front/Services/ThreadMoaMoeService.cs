using System.Text.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;

public class ThreadMoaMoeService : IDisposable
{
    private ThreadModel? messages = null;
    public event Action? OnThreadChanged = null;
    private bool hasExchangeEnded = false;
    public const string endMoeTag = "[FIN_MOE_ASSIST]";

    public ThreadMoaMoeService()
    {
        //InitializeFileWatcher();
    }

    public ThreadModel? GetMoeMoaThread()
    {
        return messages;
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
        hasExchangeEnded = false;
    }

    private void CheckNeedToModifyLastMessage()
    {
        // Change end message of MOE & make it editable by user
        if (messages != null && messages.Any())
        {
            if (messages!.Last().Source == "MOE" &&(messages!.Last().Content.Contains(endMoeTag) || messages!.Last().Content.StartsWith("Merci")))
            {
                messages![messages.Count - 1] = messages!.Last() with { Content = "Merci. Nous avons fini, j'ai tous les éléments dont j'ai besoin. Avez-vous d'autres points à aborder ?" };
                messages.Add(new MessageModel("MOA", "Ajouter des points à aborder avec le MOE si vous le souhaitez. Sinon, cliquez 'Envoyer' pour passez à l'étape de rédaction de l'US", 0));
                hasExchangeEnded = true;
            }

            messages!.RemoveLastThreadMessageFlags();

            if (!messages!.Last().IsSender)
                messages?.Last().SetAsLastThreadMessage();
        }
    }

    public bool HasExchangeEnded()
    {
        return hasExchangeEnded;
    }

    public void Dispose()
    {
    }
}
