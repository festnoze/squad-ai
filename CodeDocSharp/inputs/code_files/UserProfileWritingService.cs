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
    /// Initialize dependencies required to manage user profile writing tasks.
    /// </summary>
    /// <param name="mediator">An instance of IMediator used to handle requests and notifications.</param>
    /// <param name="customWebResource">An instance of ICustomWebResourceService used to manage custom web resources.</param>
    /// <param name="civilityService">An instance of ICivilityService used to handle civility-related tasks.</param>
    /// <param name="userQueryService">An instance of IUserProfileQueryingService used to query user profile data.</param>
    /// <param name="trackingClient">An instance of ITrackingRestClient used to track user interactions and activities.</param>
    /// <param name="logger">An instance of ILogger<IUserProfileWritingService> used for logging information and errors.</param>
    /// <param name="userRepository">An instance of IUserRepository used to access and manage user profile data.</param>
        public UserProfileWritingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserProfileQueryingService userQueryService, ITrackingRestClient trackingClient, ILogger<IUserProfileWritingService> logger, IUserRepository userRepository)
        {
            _mediator = mediator ?? throw new ArgumentNullException();
            _trackingClient = trackingClient;
            _logger = logger;
            _userRepository = userRepository;
        }


    /// <summary>
    /// Upload a CSV file containing payment reliability data.
    /// </summary>
    /// <param name="file">The CSV file containing payment reliability data to be uploaded.</param>
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
    /// Update the reliability status of a user's payment based on their Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The Salesforce ID of the user whose payment reliability status is being updated.</param>
    /// <param name="code">A unique code associated with the payment reliability status update.</param>
    /// <param name="isCsvUpload">A boolean indicating whether the update is being uploaded via CSV.</param>
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
    /// Update the review date of a user's profile.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile's review date is being updated.</param>
    /// <param name="reviewDateUtc">The UTC date and time when the review is to be updated. This parameter is optional and can be null.</param>
        public async Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDateUtc = null)
        {
            await _mediator.Send(new UserProfileReviewDateUpdateCommand(userId, reviewDateUtc));
        }


    /// <summary>
    /// Update the profile picture for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile picture is being updated.</param>
    /// <param name="fileGuid">The globally unique identifier of the file representing the new profile picture.</param>
        public async Task UpdateProfilePictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserProfilePictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the header picture for a specified user using the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose header picture is being updated.</param>
    /// <param name="fileGuid">The unique identifier for the file that will be used as the new header picture.</param>
        public async Task UpdateHeaderPictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserHeaderPictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the basic information of a user based on their ID, LinkedIn URL, and description.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose basic information is to be updated.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional and can be null.</param>
    /// <param name="aboutMe">A brief description or bio of the user. This parameter is optional and can be null.</param>
        public async Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe)
        {
            await _mediator.Send(new UserBasicInfoUpdateCommand(userId, linkedInUrl, aboutMe));
        }


    /// <summary>
    /// Update the ranking status for a specified user in a specific school.
    /// </summary>
    /// <param name="userId">The ID of the user whose ranking status needs to be updated.</param>
    /// <param name="schoolId">The ID of the school where the user's ranking status will be updated.</param>
    /// <param name="doesAppearInRanking">Specifies whether the user should appear in the ranking (true) or not (false).</param>
        public async Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking)
        {
            await _mediator.Send(new UserAppearsInRankingUpdateCommand(userId, schoolId, doesAppearInRanking));
        }


    /// <summary>
    /// Update the appearance status of a user in the learner directory based on provided parameters such as user ID, school ID, appearance status, and collaboration openness.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose appearance status is to be updated in the learner directory.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean flag indicating whether the user should appear in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean flag indicating whether the user is open to collaboration with others.</param>
        public async Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration)
        {
            await _mediator.Send(new UserAppearsInLearnerDirectoryUpdateCommand(userId, schoolId, doesAppearInLearnerDirectory, isOpenToCollaboration));
        }


    /// <summary>
    /// Update the current geographic location and timezone information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose geographic location and timezone information is being updated. This is a required parameter and should be an integer.</param>
    /// <param name="countryCode">The optional two-letter country code representing the user's current country. This parameter is a string and can be null if the country information is not available.</param>
    /// <param name="timezoneId">The optional identifier for the user's current timezone. This parameter is a string and may be null if the timezone information is not available.</param>
        public async Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId)
        {
            await _mediator.Send(new UserActualLocationUpdateCommand(userId, countryCode, timezoneId));
        }


    /// <summary>
    /// Add a user's professional experience.
    /// </summary>
    /// <param name="professionalExperienceIto">An object containing the professional experience details to be added for the user.</param>
    /// <param name="userId">The unique identifier of the user for whom the professional experience is to be added.</param>
    /// <returns>Returns a task representing the asynchronous operation.</returns>
        public async Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            return await _mediator.Send(new UserProfessionalExperienceCreateCommand(professionalExperienceIto, userId));
        }


    /// <summary>
    /// Update the professional experience information for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be updated.</param>
    /// <param name="professionalExperienceIto">The object containing updated information about the professional experience.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>
        public async Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceUpdateCommand(professionalExperienceId, professionalExperienceIto, userId));
        }


    /// <summary>
    /// Remove a user’s professional experience based on the provided experience ID and user ID.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be removed.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is to be removed.</param>
        public async Task RemoveUserProfessionalExperienceAsync(int professionalExperienceId, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceDeleteCommand(professionalExperienceId, userId));
        }


    /// <summary>
    /// Update the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose study information is to be updated.</param>
    /// <param name="studyInfos">A StudyIto object that contains the latest study information to be updated for the specified user.</param>
        public async Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos)
        {
            await _mediator.Send(new UserLatestStudyInformationsReplaceCommand(studyInfos, userId));
        }


    /// <summary>
    /// Update the notification preferences for a specified user based on provided parameters such as school ID, notification type code, and subscription statuses for email and push notifications.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose notification preferences are being updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user's notification preferences.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification (e.g., email, SMS, push notification) that the user is subscribed to.</param>
    /// <param name="isEmailSubscriptionActive">A boolean value indicating whether the user's email subscription is active. This can be null if there is no change to the email subscription status.</param>
    /// <param name="isPushSubscriptionActive">A boolean value indicating whether the user's push notification subscription is active. This can be null if there is no change to the push subscription status.</param>
        public async Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive)
        {
            await _mediator.Send(new UserNotificationRegistrationUpdateCommand(userId, schoolId, notificationTypeCode, isEmailSubscriptionActive, isPushSubscriptionActive));
        }


    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the first connection date is to be updated. It is an integer and cannot be null.</param>
    /// <param name="connectionDateUtc">The first connection date and time for the user, in UTC. This is optional and can be null. If not provided, the current date and time will be used.</param>
        public async Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDateUtc = null)
        {
            await _mediator.Send(new UserFirstConnectionDateUpdateCommand(userId, connectionDateUtc));
        }


    /// <summary>
    /// Create a user profile by obtaining the civility information, generating a pseudo name if none is provided, and then sending the user profile creation command with the provided details and default values for the avatar URL and header profile background URL.
    /// </summary>
    /// <param name="civilityId">The unique identifier representing the user's civility status. It is an integer value that determines the salutation, such as Mr., Ms., etc.</param>
    /// <param name="lastName">The last name of the user. This is a required string field that stores the user's family name.</param>
    /// <param name="firstName">The first name of the user. This is a required string field that stores the user's given name.</param>
    /// <param name="birthDate">The birth date of the user. This field stores the user's date of birth and is of type DateOnly, which represents a date without time.</param>
    /// <param name="email">The user's email address. This is a required string field used for user identification and communication.</param>
    /// <param name="pseudo">An optional pseudonym for the user. This string field allows the user to have a nickname or handle, distinct from their first and last name.</param>
    /// <param name="isOfficial">A boolean flag indicating whether the user profile is marked as an official profile. This helps differentiate official entities from regular users.</param>
    /// <param name="isTester">A boolean flag that signifies whether the user is a tester. This can be used to grant specific permissions or access for testing environments.</param>
    /// <param name="maidenName">An optional field for the user's maiden name if applicable. This string allows storage of the user's last name prior to marriage.</param>
    /// <param name="createBy">The identifier of the entity that created the user profile. This string stores information about who or what process initiated the profile creation.</param>
    /// <returns>Returns a Task containing the created UserProfile object.</returns>
        public async Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy)
        {
            var civility = _civilityService.GetCivility(civilityId);

            // If pseudo is null then generate it 
            pseudo ??= await _userQueryService.GeneratePseudoAsync(firstName, lastName);

            return await _mediator.Send(new UserProfileCreateCommand(civility!.Name, lastName, firstName, birthDate, email, pseudo!, isOfficial, isTester, _customWebResource.DefaultAvatarUrl, _customWebResource.DefaultHeaderProfileBackgroundUrl, maidenName, createBy));
        }


    /// <summary>
    /// Retrieve comments from a given code segment when it's not empty or null.
    /// </summary>
    /// <param name="code">The code segment from which comments will be retrieved. It should not be empty or null.</param>
    /// <param name="userReliability">An optional parameter representing the reliability of the user making the request. This can influence the filtering of retrieved comments.</param>
    /// <returns>Returns comments extracted from a provided code segment.</returns>
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
    /// Send a tracking event to a specified endpoint, involving data preparation, error handling, and response evaluation.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This integer value is used to determine which user is associated with the tracking event.</param>
    /// <param name="title">The title of the tracking event. This string value provides a concise description or name for the event being tracked.</param>
    /// <param name="comments">Additional comments related to the tracking event. This string allows you to include any extra information or context for the event.</param>
    /// <param name="createBy">The user or system that is creating the tracking event. This string indicates the originator of the event, used for tracking and auditing purposes.</param>
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