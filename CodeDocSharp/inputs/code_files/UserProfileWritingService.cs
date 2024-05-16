using CsvHelper;
using CsvHelper.Configuration;
using MediatR;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Localization;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.User.Application.Interfaces;
using Studi.Api.Lms.User.Application.Services.Civility;
using Studi.Api.Lms.User.Application.Services.CustomWebResource;
using Studi.Api.Lms.User.Application.Mapping;
using Studi.Api.Lms.User.Application.Services.PaymentReliability;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Common.ITOs.Interfaces;
using Studi.Api.Lms.User.Common.RepositoriesInterfaces;
using Studi.Api.Lms.User.Domain.Commands;
using Studi.Api.Lms.User.Domain.UserAggregate.Commands;
using Studi.Api.Lms.User.Localization.Error.GeneratedClasses;
using Studi.Api.Tracking.Client;
using System.Globalization;

namespace Studi.Api.Lms.User.Application.Services
{
    [ScopedService(typeof(IUserProfileWritingService))]
    public class UserProfileWritingService : IUserProfileWritingService
    {
        private readonly IMediator _mediator;
        private readonly ICustomWebResourceService _customWebResource;
        private readonly ICivilityService _civilityService;
        private readonly IUserProfileQueryingService _userQueryService;
        private readonly ILogger<IUserProfileWritingService> _logger;
        private readonly ITrackingRestClient _trackingClient;
        private readonly IUserRepository _userRepository;

    
    /// <summary>
    /// Set up a service with required components for handling user profile writing operations.
    /// </summary>
    /// <param name="mediator">A mediator instance used for handling various indirect calls and commands within the system.</param>
    /// <param name="customWebResource">An instance of ICustomWebResourceService for managing custom web resources.</param>
    /// <param name="civilityService">An instance of ICivilityService used for handling civility-related operations.</param>
    /// <param name="userQueryService">An instance of IUserProfileQueryingService to query user profile data.</param>
    /// <param name="trackingClient">An instance of ITrackingRestClient for sending tracking information to the server for logging and analysis.</param>
    /// <param name="logger">A logger instance for logging information within the UserProfileWritingService.</param>
    /// <param name="userRepository">An instance of IUserRepository used for managing user data in the repository.</param>
    public UserProfileWritingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserProfileQueryingService userQueryService, ITrackingRestClient trackingClient, ILogger<IUserProfileWritingService> logger, IUserRepository userRepository)
        {
            _mediator = mediator ?? throw new ArgumentNullException();
            _trackingClient = trackingClient;
            _logger = logger;
            _userRepository = userRepository;
        }

    
    /// <summary>
    /// Upload a CSV file to check payment reliability. Deserialize the CSV file content, validate its structure, and process the valid data entries to update the existing payment reliability records. Handle any exceptions that may occur during the process and log the pertinent error messages.
    /// </summary>
    /// <param name="file">The CSV file that contains the payment reliability data to be uploaded for tracking information.</param>
    public async Task UploadCsvFilePaymentReliabilityAsync(IFormFile file)
        {
            try
            {
                var configurationMapping = new CsvConfiguration(CultureInfo.InvariantCulture)
                {
                    HasHeaderRecord = true,
                    Delimiter = ";",
                };

                using (var streamReader = new StreamReader(file.OpenReadStream()))
                using (var csv = new CsvReader(streamReader, configurationMapping))
                {
                    csv.Context.RegisterClassMap<MappingCsvPaymentReliabilityMap>();
                    var records = csv.GetRecords<MappingCsvPaymentReliability>()
                                     .Select(q => new MappingCsvPaymentReliability
                                     {
                                         Name = q.Name,
                                         PaymentReliabilityCode = q.PaymentReliabilityCode.ToLower(),
                                         AccountId = q.AccountId,
                                         AccountId18Digits = q.AccountId18Digits
                                     })
                                     .Where(q => !string.IsNullOrEmpty(q.PaymentReliabilityCode))
                                     .ToList();

                    foreach (var record in records)
                    {
                        await UpdatePaymentReliabilityAsync(record.AccountId18Digits, record.PaymentReliabilityCode, true);
                    }
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error while processing csv upload");
            }
        }

    
    /// <summary>
    /// Update the payment reliability status based on the provided Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The unique identifier for a Salesforce entity, used to track and reference specific records.</param>
    /// <param name="code">The unique code associated with the payment reliability update, which may correspond to a specific transaction or operation.</param>
    /// <param name="isCsvUpload">Indicates whether the data being sent is part of a CSV upload (true) or not (false).</param>
    public async Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload)
        {
            Guard.Against.NullOrEmpty(salesforceId, ErrorCode.Api.Lms.User.DataValidation.Common.SalesforceId.NullOrEmpty);

            var userId = await _userRepository.GetUserIdBySalesforceIdAsync(salesforceId);

            if (userId != 0)
            {
                var userReliability = await _userRepository.GetUserReliabilityByUserId(userId);
                string comments = GetCommentsFromCode(code, userReliability);

                await _userRepository.UpdatePaymentReliabilityAsync(userId, code);
                await SendTrackingAsync(userId, "Mise à jour de la situation de paiement", comments, "Salesforce");
            }
            else if (userId == 0 && !isCsvUpload)
            {
                Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Command.PaymentReliability.UserIdNull);
            }
            else
            {
                _logger.LogWarning($"L'utilisateur avec l'id salesforce {salesforceId} donné n'a pas été mis à jour");
            }
        }

    
    /// <summary>
    /// Update the profile review date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile review date is to be updated. This parameter is required and should be an integer.</param>
    /// <param name="reviewDateUtc">The DateTime value representing the new review date in Coordinated Universal Time (UTC). This parameter is optional and can be null.</param>
    public async Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDateUtc = null)
        {
            await _mediator.Send(new UserProfileReviewDateUpdateCommand(userId, reviewDateUtc));
        }

    
    /// <summary>
    /// Update the profile picture for a specified user by using their user ID and file GUID.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This is used to specify which user's profile picture is being updated.</param>
    /// <param name="fileGuid">The globally unique identifier of the file. This is used to specify the new profile picture file to be uploaded and updated for the user.</param>
    public async Task UpdateProfilePictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserProfilePictureUpdateCommand(userId, fileGuid));
        }

    
    /// <summary>
    /// Update the header picture for a specific user using their ID and the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This parameter is used to specify which user's data is to be retrieved or manipulated.</param>
    /// <param name="fileGuid">The globally unique identifier for the file. This parameter is used to identify the specific file for which the header picture is being updated.</param>
    public async Task UpdateHeaderPictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserHeaderPictureUpdateCommand(userId, fileGuid));
        }

    
    /// <summary>
    /// Update basic information for a specified user including LinkedIn URL and personal description.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose information is being updated.</param>
    /// <param name="linkedInUrl">An optional string containing the URL of the user's LinkedIn profile. This may be null if no URL is provided.</param>
    /// <param name="aboutMe">An optional string containing a brief description or biography about the user. This may be null if no description is provided.</param>
    public async Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe)
        {
            await _mediator.Send(new UserBasicInfoUpdateCommand(userId, linkedInUrl, aboutMe));
        }

    
    /// <summary>
    /// Update the ranking status for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. It is used to distinguish between different users in the system.</param>
    /// <param name="schoolId">The unique identifier of the school. It helps in identifying the specific school to which the data pertains.</param>
    /// <param name="doesAppearInRanking">A boolean value that indicates whether the ranking should be displayed for the user in the system or not.</param>
    public async Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking)
        {
            await _mediator.Send(new UserAppearsInRankingUpdateCommand(userId, schoolId, doesAppearInRanking));
        }

    
    /// <summary>
    /// Update the learner directory status and collaboration openness for a specified user within a particular school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user.</param>
    /// <param name="schoolId">The unique identifier for the school.</param>
    /// <param name="doesAppearInLearnerDirectory">Indicates whether the user appears in the learner directory.</param>
    /// <param name="isOpenToCollaboration">Indicates whether the user is open to collaboration.</param>
    public async Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration)
        {
            await _mediator.Send(new UserAppearsInLearnerDirectoryUpdateCommand(userId, schoolId, doesAppearInLearnerDirectory, isOpenToCollaboration));
        }

    
    /// <summary>
    /// Update the actual location for a specified user based on their user ID, country code, and timezone ID.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose location is being tracked.</param>
    /// <param name="countryCode">An optional string parameter representing the country code where the user is located. It may be null.</param>
    /// <param name="timezoneId">An optional string parameter representing the timezone ID of the user's current location. It may be null.</param>
    public async Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId)
        {
            await _mediator.Send(new UserActualLocationUpdateCommand(userId, countryCode, timezoneId));
        }

    
    /// <summary>
    /// Add a new professional experience entry for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">The ProfessionalExperienceIto object that contains the details of the user's professional experience to be added.</param>
    /// <param name="userId">The unique identifier of the user for whom the professional experience is being added.</param>
    /// <returns>Returns a Task representing the asynchronous operation of adding a professional experience.</returns>
    public async Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            return await _mediator.Send(new UserProfessionalExperienceCreateCommand(professionalExperienceIto, userId));
        }

    
    /// <summary>
    /// Update a user's professional experience details using the provided experience ID and data.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience that needs to be updated.</param>
    /// <param name="professionalExperienceIto">The object containing the updated details of the professional experience.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>
    public async Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceUpdateCommand(professionalExperienceId, professionalExperienceIto, userId));
        }

    
    /// <summary>
    /// Remove a professional experience record for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the user's professional experience that should be removed.</param>
    /// <param name="userId">The unique identifier of the user for whom the professional experience should be removed.</param>
    public async Task RemoveUserProfessionalExperienceAsync(int professionalExperienceId, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceDeleteCommand(professionalExperienceId, userId));
        }

    
    /// <summary>
    /// Update the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose tracking information is being managed.</param>
    /// <param name="studyInfos">The detailed study information to be logged and analyzed for the user.</param>
    public async Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos)
        {
            await _mediator.Send(new UserLatestStudyInformationsReplaceCommand(studyInfos, userId));
        }

    
    /// <summary>
    /// Update the notification preferences for a specified user based on various parameters.
    /// </summary>
    /// <param name="userId">The ID of the user who will have their notification settings updated.</param>
    /// <param name="schoolId">The ID of the school associated with the user's notification settings.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to update (e.g., email, push).</param>
    /// <param name="isEmailSubscriptionActive">A flag indicating whether the email subscription is active (null if no change).</param>
    /// <param name="isPushSubscriptionActive">A flag indicating whether the push subscription is active (null if no change).</param>
    public async Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive)
        {
            await _mediator.Send(new UserNotificationRegistrationUpdateCommand(userId, schoolId, notificationTypeCode, isEmailSubscriptionActive, isPushSubscriptionActive));
        }

    
    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. It is a required integer parameter used to identify the user in the system.</param>
    /// <param name="connectionDateUtc">The date and time of the user's first connection in UTC. This parameter is optional and, if not provided, will default to null.</param>
    public async Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDateUtc = null)
        {
            await _mediator.Send(new UserFirstConnectionDateUpdateCommand(userId, connectionDateUtc));
        }

    
    /// <summary>
    /// Create a user profile with specified details, ensuring civility and generating a pseudo if not provided.
    /// </summary>
    /// <param name="civilityId">Identifier representing the civility of the user (e.g., Mr, Ms).</param>
    /// <param name="lastName">The last name of the user.</param>
    /// <param name="firstName">The first name of the user.</param>
    /// <param name="birthDate">The birth date of the user.</param>
    /// <param name="email">The email address of the user.</param>
    /// <param name="pseudo">The optional pseudonym or nickname of the user.</param>
    /// <param name="isOfficial">Indicates if the user is an official user.</param>
    /// <param name="isTester">Indicates if the user is a tester.</param>
    /// <param name="maidenName">The optional maiden name of the user.</param>
    /// <param name="createBy">Identifier of the user or process that created this profile.</param>
    /// <returns>Returns a Task<UserProfile> representing the newly created user profile.</returns>
    public async Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy)
        {
            var civility = _civilityService.GetCivility(civilityId);

            // If pseudo is null then generate it 
            pseudo ??= await _userQueryService.GeneratePseudoAsync(firstName, lastName);

            return await _mediator.Send(new UserProfileCreateCommand(civility!.Name, lastName, firstName, birthDate, email, pseudo!, isOfficial, isTester, _customWebResource.DefaultAvatarUrl, _customWebResource.DefaultHeaderProfileBackgroundUrl, maidenName, createBy));
        }

     
    /// <summary>
    /// Check if the provided code is not null or empty.
    /// </summary>
    /// <param name="code">The string code that identifies the specific tracking information to be sent to the server.</param>
    /// <param name="userReliability">The optional IUserReliabilityIto object which provides additional user reliability data for more detailed logging and analysis purposes.</param>
    /// <returns>Returns extracted comments from the provided code string.</returns>
   private string GetCommentsFromCode(string code, IUserReliabilityIto? userReliability)
        {
            string sentenceCode = string.Empty;

            if (!string.IsNullOrEmpty(code))
            {
                if (code == PaymentReliabilityCode.Echeance.ToLower())
                {
                    sentenceCode = "Ce client a une échéance impayée.";
                }
                else if (code == PaymentReliabilityCode.Contentieux.ToLower())
                {
                    sentenceCode = "Ce client est en contentieux.";
                }
            }

            if (userReliability is not null && string.IsNullOrEmpty(code))
            {
                return "Situation régularisée";
            }
            return $"{sentenceCode} Veuillez contacter le service Recouvrement.";
        }

     
    /// <summary>
    /// Get and send tracking information to the server for logging and analysis purposes.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This is used to associate the tracking information with a specific user.</param>
    /// <param name="title">The title or name associated with the tracking event. This provides a brief, recognizable label for the event.</param>
    /// <param name="comments">Additional comments or details about the tracking event. This is used to provide more context or information about what is being tracked.</param>
    /// <param name="createBy">The identifier or name of the person or system that created the tracking information. This helps to track the origin of the data.</param>
   private async Task SendTrackingAsync(int userId, string title, string comments, string createBy)
        {
            try
            {
                var source = await _trackingClient.GetTrackingSourceByCodeAsync("INFORMATION");
                var subReason = await _trackingClient.GetTrackingSubReasonByCodeAsync("SUJET_COMPTABILITE");

                await _trackingClient.CreateTrackingAsync(new Tracking.Client.Models.BindingModels.UserTrackingCreateBM
                {
                    userId = userId,
                    sourceId = source.Id,
                    subReasonId = subReason.Id,
                    type = "sortant",
                    title = title,
                    comments = comments,
                    createdDate = StudiTime.Now,
                    createdBy = createBy
                });
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error while processing tracking client request");
            }
        }
    }
}