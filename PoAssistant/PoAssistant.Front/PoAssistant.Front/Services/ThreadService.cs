using System.Text.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;

public class ThreadService : IDisposable
{
    private ThreadModel? messages = null;
    public event Action? OnThreadChanged = null;
    public const string endMoeTag = "[FIN_MOE_ASSIST]";

    public ThreadService()
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

    private void CheckNeedToModifyLastMessage()
    {
        // Change end message of MOE & make it editable by user
        if (messages != null && messages.Any())
        {
            if (messages!.Last().Content.Contains(endMoeTag))
            {
                messages![messages.Count - 1] = messages!.Last() with { Content = "Merci. Je n'ai plus d'autres questions. Avez-vous d'autres points à aborder ? Sinon, cliquez sur 'Suivant'" };
                messages.Add(new MessageModel("MOA", "Ajouter des points à aborder avec le MOE si vous le souhaitez", 0));
            }

            messages!.RemoveLastThreadMessageFlags();

            if (!messages!.Last().IsSender)
                messages?.Last().SetAsLastThreadMessage();
        }
    }

    public void Dispose()
    {
    }
}
