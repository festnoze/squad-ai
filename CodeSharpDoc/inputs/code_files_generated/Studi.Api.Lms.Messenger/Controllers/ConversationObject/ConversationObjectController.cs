using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Studi.Api.Lms.Messenger.Application.Services.ConversationObjectService;
using Studi.Api.Lms.Messenger.Controllers.ConversationObject.Mapping;
using Studi.Api.Lms.Messenger.ExchangeDataContract.v1.ConversationObject.ResponseModels;
using Studi.Api.Lms.Messenger.Utils.Middleware;
using Swashbuckle.AspNetCore.Annotations;
using System.Net;

namespace Studi.Api.Lms.Messenger.Controllers.ConversationObject;

[ApiController]
[Route("v{version:apiVersion}/conversation-objects")]
[Authorize]
public class ConversationObjectController : ControllerBase
{
    private readonly IConversationObjectService _conversationObjectService;


    /// <summary>
    /// Instantiate a ConversationObjectController object with a ConversationObjectService dependency for managing conversation objects.
    /// </summary>
    /// <param name="conversationObjectService">The IConversationObjectService parameter represents an instance of the IConversationObjectService interface, which is used for managing conversation objects.</param>
    /// <param name="ConversationObjectController">The ConversationObjectController parameter represents an instance of the ConversationObjectController class, which serves as a constructor for the containing class of the same name. This method is used to instantiate a ConversationObjectController object with a ConversationObjectService dependency for managing conversation objects.</param>
    public ConversationObjectController(IConversationObjectService conversationObjectService)
    {
        _conversationObjectService = conversationObjectService;
    }

    [HttpGet("internal-services/{internalServiceCode}")]
    [ApiVersion("1")]
    [SwaggerOperation("Retrieves ConversationObjects associated with a specific interne service.")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(IEnumerable<ConversationObjectResponseModel>))]
    [SkipCheckParamsAgainstLmsToken]

    /// <summary>
    /// Retrieve conversation objects asynchronously and convert them to response models.
    /// </summary>
    /// <param name="string">The name of the parameter (it's always a single word. Also exclude the type of the parameter which may come firstly)</param>
    /// <param name="internalServiceCode">The name of the parameter (it's always a single word. Also exclude the type of the parameter which may come firstly)</param>
    /// <param name="GetConversationObjectsAsync">The name of the parameter (it's always a single word. Also exclude the type of the parameter which may come firstly)</param>
    /// <param name="Retrieve conversation objects asynchronously and convert them to response models.">The name of the parameter (it's always a single word. Also exclude the type of the parameter which may come firstly)</param>
    /// <returns>Returns converted response models retrieved asynchronously from conversation objects.</returns>
    public async Task<IEnumerable<ConversationObjectResponseModel>> GetConversationObjectsAsync(string internalServiceCode)
    {
        var conversationObjects = await _conversationObjectService.GetConversationObjectsAsync(internalServiceCode);
        return conversationObjects.Select(co => co.ToResponseModel());
    }

    [HttpGet("{conversationObjectCode}/conversation-sub-objects")]
    [ApiVersion("1")]
    [SwaggerOperation("Retrieves ConversationSubObjects associated with a specific ConversationObject.")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(IEnumerable<ConversationSubObjectResponseModel>))]
    [SkipCheckParamsAgainstLmsToken]

    /// <summary>
    /// Retrieve conversation sub objects asynchronously based on the conversation object code and return them as response models.
    /// </summary>
    /// <param name="conversationObjectCode">The name of the parameter (it's always a single word. Also exclude the type of the parameter which may come firstly)</param>
    /// <param name="methodPurpose">The generated description for the parameter</param>
    /// <returns>Returns a list of conversation sub objects as response models.</returns>
    public async Task<IEnumerable<ConversationSubObjectResponseModel>> GetConversationSubObjectsAsync(string conversationObjectCode)
    {
        var conversationSubObjects = await _conversationObjectService.GetConversationSubObjectsAsync(conversationObjectCode);
        return conversationSubObjects.Select(cso => cso.ToResponseModel());
    }


    /// <summary>
    /// Retrieve internal services asynchronously and convert them to response models.
    /// </summary>
    /// <returns>Returns a collection of internal services as response models.</returns>
    [HttpGet("internal-services")]
    [ApiVersion("1")]
    [SwaggerOperation("Retrieves the list of interne services.")]
    [SwaggerResponse((int)HttpStatusCode.OK, Type = typeof(IEnumerable<InternalServiceResponseModel>))]
    [SkipCheckParamsAgainstLmsToken]
    public async Task<IEnumerable<InternalServiceResponseModel>> GetInternalServicesAsync()
    {
        var internalServices = await _conversationObjectService.GetInternalServicesAsync();
        return internalServices.Select(intServ => intServ.ToResponseModel());
    }
}