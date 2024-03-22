using System.Text.Json;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;

public class UserStoryService
{
    private UserStoryModel? userStory = null;
    public event Action? OnUserStoryChanged = null;
    public const string endPmTag = "[FIN_PM_ASSIST]";
    private NavigationService _navigationService;
    public UserStoryService(NavigationService navigationService)
    {
        _navigationService = navigationService;
        //InitializeFileWatcher();
    }

    public void SetPoUserStory(UserStoryModel userStory)
    {
        this.userStory = userStory;
        //_navigationService.NavigateToPoPage();
        OnUserStoryChanged?.Invoke();
    }

    public UserStoryModel? GetPoUserStory()
    {
        return userStory;
    }
}
