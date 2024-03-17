using Microsoft.AspNetCore.Mvc;
using Newtonsoft.Json;
using PoAssistant.Front.Data;
using PoAssistant.Front.Services;

namespace PoAssistant.Front.Controller;

[ApiController]
[Route("[controller]")]
public class FrontendProxyController
{
    public FrontendProxyController(ThreadMoaMoeService threadService, UserStoryService userStoryService)
    {
        _threadService = threadService;
        _userStoryService = userStoryService;
    }

    private readonly ThreadMoaMoeService _threadService;
    private readonly UserStoryService _userStoryService;

    [HttpPost("moa-moe/new-message")]
    public void NewMoaMoeMessage([FromBody] MessageModel newMessage)
    {
        _threadService.AddNewMessage(newMessage);
    }


    [HttpDelete("moa-moe/delete")]
    public void DeleteMoaMoeThread()
    {
        _threadService.DeleteMoaMoeThread();
    }

    [HttpPost("po/us")]
    public void ReadyPoUserStory([FromBody] UserStoryModel userStory)
    {
        //var tmp = JsonConvert.DeserializeObject<UserStoryModel>(userStory);
        _userStoryService.SetPoUserStory(userStory);
    }


    [HttpGet("ping")]
    public string Ping()
    {
        return "pong";
    }
}
