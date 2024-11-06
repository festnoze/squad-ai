using System.Text.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;

public class UserStoryService
{
    private List<UserStoryModel>? userStories = null;
    private int currentUsIndex = 0;
    public event Action? OnUserStoryChanged = null;

    public UserStoryService()
    {
    }

    public void SetPoUserStory(IEnumerable<UserStoryModel> userStories)
    {
        this.userStories = userStories.ToList();
        currentUsIndex = 0;
        OnUserStoryChanged?.Invoke();
    }

    public void NavigateToNextUS()
    {
        if (userStories is null)
            return;

        if (currentUsIndex < userStories!.Count - 1)
            currentUsIndex++;
    }

    public void NavigateToPreviousUS()
    {
        if (userStories is null)
            return;

        if (currentUsIndex > 0)
            currentUsIndex--;
    }

    public UserStoryModel? GetPoUserStory()
    {
        return userStories?[currentUsIndex];
    }
}
