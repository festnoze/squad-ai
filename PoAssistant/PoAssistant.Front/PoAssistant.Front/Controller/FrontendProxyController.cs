using Microsoft.AspNetCore.Mvc;
using PoAssistant.Front.Data;
using PoAssistant.Front.Services;
using System.Text;
using System.IO;
using PoAssistant.Front.Helpers;

namespace PoAssistant.Front.Controller;

[ApiController]
[Route("[controller]")]
public class FrontendProxyController : ControllerBase
{
    public FrontendProxyController(ThreadMetierCdPService threadService, UserStoryService userStoryService)
    {
        _threadService = threadService;
        _userStoryService = userStoryService;
    }

    private readonly ThreadMetierCdPService _threadService;
    private readonly UserStoryService _userStoryService;

    /// <summary>
    /// Send the brief if ready, or an empty string otherwise
    /// </summary>
    /// <returns></returns>
    [HttpGet("metier/brief")]
    public string GetMetierBriefIfReady()
    {
        return _threadService.GetMetierBriefIfReady();
    }

    /// <summary>
    /// Send the latest business expert answer if validated, or an empty string otherwise
    /// </summary>
    /// <returns></returns>
    [HttpGet("metier/last-answer")]
    public string GetLatestBusinessExpertAnswerIfValidated()
    {
        return _threadService.GetLatestBusinessExpertAnswerIfValidated();
    }

    [HttpPost("metier-po/new-message")]
    public void NewMetierPoMessage([FromBody] MessageModel newMessage)
    {
        _threadService.AddNewMessage(newMessage);
    }

    [HttpDelete("metier-po/delete-all")]
    public void DeleteMetierPoThread()
    {
        _threadService.DeleteMetierPoThread();
    }

    [HttpPost("po/us")]
    public void ReadyPoUserStory([FromBody]IEnumerable<UserStoryModel> userStories)
    {
        _threadService.EndMetierMetierExchange();
        _userStoryService.SetPoUserStory(userStories);
    }

    [HttpPost("metier-po/new-message/stream")]
    public async Task ReceiveMessageAsStream()
    {
        var buffer = new StringBuilder();
        _threadService.InitStreamMessage();
        string? newWord = string.Empty;
        using (var reader = new StreamReader(Request.Body, Encoding.UTF8))
        {
            //StreamReaderExtensions.AddNewCharDelimiters(StreamHelper.NewLineForStream);
            while ((newWord = await reader.ReadWordAsync()) != null)
            {
                _threadService.DisplayStreamMessage(newWord);
            }
        }
        _threadService.EndsStreamMessage();
    }

    [HttpPost("metier-po/update-last-message")]
    public void UpdateLastMetierPoMessage([FromBody] MessageModel newMessage)
    {
        _threadService.UpdateLastMessage(newMessage);
    }

    [HttpGet("ping")]
    public string Ping()
    {
        return "pong";
    }
}
