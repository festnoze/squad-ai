using System.Linq;
using System.Text.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;

public class ThreadMetierPoService : IDisposable
{
    private ThreadModel messages = null!;
    public event Action? OnThreadChanged = null;
    private bool isWaitingForLLM = false;
    public const string endPoTag = "[FIN_PO_ASSIST]";

    public ThreadMetierPoService()
    {
        if (messages is null)
        {
            messages = new ThreadModel("Métier", string.Empty, true);
            isWaitingForLLM = false;
        }
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

        messages!.Add(newMessage);
        CheckNeedToModifyLastMessage();

        if (newMessage.Source == "Métier")
            isWaitingForLLM = false;

        OnThreadChanged?.Invoke();
    }

    public void DeleteMetierPoThread()
    {
        messages = new ThreadModel();
        isWaitingForLLM = false;
        OnThreadChanged?.Invoke();
    }

    public void EndMetierMetierExchange()
    {

        messages!.Add(new MessageModel("PO", "Le PO a maintenant rédigé la User Story et défini les use cases.", 0, true));
        isWaitingForLLM = false;
        OnThreadChanged?.Invoke();
    }

    private void CheckNeedToModifyLastMessage()
    {
        // Change end message of PO & make it editable by user
        if (messages != null && messages.Any())
        {
            if (messages!.Last().Source == "PO" &&(messages!.Last().Content.Contains(endPoTag) || messages!.Last().Content.StartsWith("Merci")))
            {
                messages!.Last().ChangeContent("Merci. Nous avons fini, j'ai tous les éléments dont j'ai besoin. Avez-vous d'autres points à aborder ?");
                messages.Add(new MessageModel("Métier", "Ajouter des points à aborder avec le PO si vous le souhaitez. Sinon, cliquez 'Envoyer' pour passez à l'étape de rédaction de l'US", 0));
                isWaitingForLLM = false;
            }

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
        if (messages != null && messages.Count() == 1 && !messages!.Last().IsSavedMessage)
            messages!.Last().ChangeContent(string.Empty);
    }

    public void ValidateMetierAnswer()
    {
        if (!messages?.Any() ?? true)
            return;

        if (messages!.Count() == 1)
            SaveMetierBrief();
        else
            SaveMetierAnswer();
    }

    private void SaveMetierBrief()
    {
        var needFilePath = "..\\..\\Shared\\brief.txt";
        messages!.Last().IsSavedMessage = true;
        File.WriteAllText(needFilePath, messages!.Single().Content);
    }

    private void SaveMetierAnswer()
    {
        var filePath = "..\\..\\Shared\\moa_answer.txt";
        if (messages == null || messages.Last().Source != "Métier")
            throw new Exception("Le dernier message n'est pas présent ou n'est pas du Métier");
     
        messages!.Last().IsSavedMessage = true;
        File.WriteAllText(filePath, messages!.Last().Content);
    }

    public void Dispose()
    {}
}
