using System.Linq;
using System.Text.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;

public class ThreadMoaMoeService : IDisposable
{
    private ThreadModel messages = null!;
    public event Action? OnThreadChanged = null;
    private bool isWaitingForLLM = false;
    public const string endMoeTag = "[FIN_MOE_ASSIST]";

    public ThreadMoaMoeService()
    {
        if (messages is null)
        {
            messages = new ThreadModel("MOA", string.Empty, true);
            isWaitingForLLM = false;
        }
    }

    public ThreadModel GetMoeMoaThread()
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

        if (newMessage.Source == "MOA")
            isWaitingForLLM = false;

        OnThreadChanged?.Invoke();
    }

    public void DeleteMoaMoeThread()
    {
        messages = new ThreadModel();
        isWaitingForLLM = false;
        OnThreadChanged?.Invoke();
    }

    public void EndMoaMoaExchange()
    {

        messages!.Add(new MessageModel("MOE", "Le PO a maintenant rédigé la User Story et défini les use cases.", 0, true));
        isWaitingForLLM = false;
        OnThreadChanged?.Invoke();
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

    public bool IsWaitingForLLM()
    {
        return isWaitingForLLM;
    }

    public void EditingLastMessage()
    {
        if (messages != null && messages.Count() == 1 && !messages!.Last().IsSavedMessage)
            messages!.Last().ChangeContent(string.Empty);
    }

    public void ValidateMoaAnswer()
    {
        if (!messages?.Any() ?? true)
            return;

        if (messages!.Count() == 1)
            SaveMoaNeed();
        else
            SaveMoaAnswer();
    }

    private void SaveMoaNeed()
    {
        var needFilePath = "..\\..\\need.txt";
        messages!.Last().IsSavedMessage = true;
        File.WriteAllText(needFilePath, messages!.Single().Content);
    }

    private void SaveMoaAnswer()
    {
        var filePath = "..\\..\\moa_answer.txt";
        if (messages == null || messages.Last().Source != "MOA")
            throw new Exception("Le dernier message n'est pas présent ou n'est pas du MOA");
     
        messages!.Last().IsSavedMessage = true;
        File.WriteAllText(filePath, messages!.Last().Content);
    }

    public void Dispose()
    {}
}
