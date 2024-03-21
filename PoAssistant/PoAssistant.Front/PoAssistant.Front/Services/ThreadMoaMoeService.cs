using System.Linq;
using System.Text.Json;
using PoAssistant.Front.Data;
using PoAssistant.Front.Helpers;

namespace PoAssistant.Front.Services;

public class ThreadMetierPoService : IDisposable
{
    private ThreadModel messages = null!;
    public event Action? OnThreadChanged = null;
    private bool isWaitingForLLM = false;
    public const string endPoTag = "[FIN_PO_ASSIST]";

    public ThreadMetierPoService()
    {
        InitializeThread();
    }

    private void InitializeThread()
    {
        if (messages is null || !messages.Any())
        {
            messages = new ThreadModel("Métier", string.Empty, true);
            isWaitingForLLM = false;
        }
    }

    public string GetMetierBriefIfReady()
    {
        if (messages is null ||
            !messages.Any() || 
            !messages!.First().IsSavedMessage || 
            messages!.First().Content.Length < 1)
            return string.Empty;

        return messages!.First().Content;
    }

    public string GetLatestBusinessExpertAnswerIfValidated()
    {
        if (messages == null ||
            !messages.Any() ||
            messages.Last().Source != "Métier" ||
            !messages!.Last().IsSavedMessage ||
            messages!.Last().Content.Length < 1)
            return string.Empty;

        return messages!.Last().Content;
    }

    public ThreadModel GetPoMetierThread()
    {
        return messages!;
    }

    public bool IsEditingLastMessage()
    {
        return messages.Last().IsLastThreadMessage && !messages.Last().IsSavedMessage;
    }

    public void AddNewMessage(MessageModel newMessage)
    {
        if (messages is null)
            messages = new ThreadModel();

        newMessage.IsSavedMessage = false;
        messages!.Add(newMessage);

        isWaitingForLLM = IsWaiting();
        RefreshLastMessageInThread();

        OnThreadChanged?.Invoke();
    }

    public void DeleteMetierPoThread()
    {
        messages = new ThreadModel();
        InitializeThread();
        OnThreadChanged?.Invoke();
    }

    public void EndMetierMetierExchange()
    {
        messages!.Add(new MessageModel("PO", "Le PO a maintenant rédigé la User Story et défini les use cases.", 0, true));
        isWaitingForLLM = false;
        NotifyForUserStoryReady();
        OnThreadChanged?.Invoke();
    }

    private bool IsWaiting()
    {
        if (messages != null && messages.Any())
        {
            // Change end message of PO & make it editable by user
            if (messages!.Last().IsSender)
            {
                if (messages!.Last().Content.Contains(endPoTag) || !messages!.Last().Content.Contains("?"))
                {
                    messages!.Last().ChangeContent("Merci. Nous avons fini, j'ai tous les éléments dont j'ai besoin. Avez-vous d'autres points à aborder ?");
                    messages.Add(new MessageModel("Métier", "Ajouter des points à aborder avec le PO si vous le souhaitez. Sinon, cliquez 'Envoyer' pour passez à l'étape de rédaction de l'US", 0, false, true));
                    return false;
                }
                return true;
            }

            if (!messages!.Last().IsSender)
                return false;
        }
        
        return false;
    }

    private void RefreshLastMessageInThread()
    {
        if (messages != null && messages.Any())
        {
            messages!.RemoveLastThreadMessageFlags();

            if (!messages!.Last().IsSender)
                messages?.Last().SetAsLastThreadMessage();
        }
    }

    public bool IsWaitingForLLM()
    {
        return isWaitingForLLM;
    }

    public void EditingLastMessage()
    {
        if (messages != null && messages.Last().IsEndMessage)
            messages!.Last().ChangeContent(string.Empty);
    }

    public void ValidateMetierAnswer()
    {
        if (!messages?.Any() ?? true)
            return;
        
        messages!.Last().IsSavedMessage = true;
    }

    public event Action? UserStoryReadyNotification;

    protected virtual void NotifyForUserStoryReady()
    {
        UserStoryReadyNotification?.Invoke();
    }

    public void DoEndBusinessPoExchange()
    {
        messages.Last().Content = "[ENDS_EXCHANGE]";
        messages.Last().IsSavedMessage = true;
    }

    public void Dispose()
    {
    }

    public void InitStreamMessage()
    {
        if (messages is null)
            messages = new ThreadModel();

        var newMessage = new MessageModel("test", string.Empty, 0, false);
        messages!.Add(newMessage);

        isWaitingForLLM = false;
        RefreshLastMessageInThread();
    }

    public void DisplayStreamMessage(string? messageChunk)
    {
        if (messageChunk != null)
        {
            messages!.Last().Content += messageChunk.Replace(StreamHelper.NewLineForStream, StreamHelper.WindowsNewLine);
            OnThreadChanged?.Invoke();
        }
    }
}
