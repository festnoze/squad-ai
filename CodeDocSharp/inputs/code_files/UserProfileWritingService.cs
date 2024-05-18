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
    /// Initialize dependencies for a user profile writing service.
    /// </summary>
    /// <param name="mediator">The mediator for handling communication between components.</param>
    /// <param name="customWebResource">Service for handling custom web resources.</param>
    /// <param name="civilityService">Service for managing civility-related operations.</param>
    /// <param name="userQueryService">Service for querying user profiles.</param>
    /// <param name="trackingClient">REST client for tracking operations.</param>
    /// <param name="logger">Logger instance for logging user profile writing service activities.</param>
    /// <param name="userRepository">Repository for accessing and managing user data.</param>
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
    /// <param name="file">The CSV file that contains the payment reliability data to be uploaded.</param>
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
    /// Update the payment reliability status based on the specified Salesforce ID after ensuring the ID is neither null nor empty and retrieving the corresponding user ID.
    /// </summary>
    /// <param name="salesforceId">The Salesforce ID used to identify the specific record. The method ensures that this ID is neither null nor empty before proceeding.</param>
    /// <param name="code">A specific code associated with the payment reliability update. This might be related to a status or result code.</param>
    /// <param name="isCsvUpload">A boolean value indicating whether the update is based on a CSV upload. Helps in determining the source of the update.</param>
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
    /// Update the review date of a user profile using the specified UTC date and user ID.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile review date will be updated.</param>
    /// <param name="reviewDateUtc">The UTC date to set as the review date for the user's profile. If null, no date will be updated.</param>
        public async Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDateUtc = null)
        {
            await _mediator.Send(new UserProfileReviewDateUpdateCommand(userId, reviewDateUtc));
        }


    /// <summary>
    /// Update the profile picture for a specified user by sending a corresponding command.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile picture is to be updated.</param>
    /// <param name="fileGuid">The globally unique identifier of the file that contains the new profile picture.</param>
        public async Task UpdateProfilePictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserProfilePictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the header picture for a specified user based on a provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose header picture is to be updated.</param>
    /// <param name="fileGuid">The GUID representing the file to be used as the new header picture.</param>
        public async Task UpdateHeaderPictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserHeaderPictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the basic information of a user with specified details including LinkedIn URL and a short description.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose basic information is to be updated.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional.</param>
    /// <param name="aboutMe">The short description or bio of the user. This parameter is optional.</param>
        public async Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe)
        {
            await _mediator.Send(new UserBasicInfoUpdateCommand(userId, linkedInUrl, aboutMe));
        }


    /// <summary>
    /// Update a user's ranking status within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose ranking status is being updated.</param>
    /// <param name="schoolId">The unique identifier for the school where the user's ranking status will be updated.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether the user appears in the ranking or not.</param>
        public async Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking)
        {
            await _mediator.Send(new UserAppearsInRankingUpdateCommand(userId, schoolId, doesAppearInRanking));
        }


    /// <summary>
    /// Update the learner directory status of a specified user with the provided parameters.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose learner directory status is to be updated.</param>
    /// <param name="schoolId">The identifier of the school associated with the user.</param>
    /// <param name="doesAppearInLearnerDirectory">Specifies whether the user should appear in the learner directory.</param>
    /// <param name="isOpenToCollaboration">Indicates if the user is open to collaboration with others.</param>
        public async Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration)
        {
            await _mediator.Send(new UserAppearsInLearnerDirectoryUpdateCommand(userId, schoolId, doesAppearInLearnerDirectory, isOpenToCollaboration));
        }


    /// <summary>
    /// Update the current location information for a specified user, including country code and timezone ID.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose location information is being updated.</param>
    /// <param name="countryCode">The country code representing the user's current country. This parameter is optional.</param>
    /// <param name="timezoneId">The timezone ID representing the user's current timezone. This parameter is optional.</param>
        public async Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId)
        {
            await _mediator.Send(new UserActualLocationUpdateCommand(userId, countryCode, timezoneId));
        }


    /// <summary>
    /// Add a professional experience entry for a specific user.
    /// </summary>
    /// <param name="professionalExperienceIto">The professional experience information to be added for the user.</param>
    /// <param name="userId">The unique identifier of the user for whom the professional experience is being added.</param>
    /// <returns>Returns a task representing the asynchronous operation.</returns>
        public async Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            return await _mediator.Send(new UserProfessionalExperienceCreateCommand(professionalExperienceIto, userId));
        }


    /// <summary>
    /// Update the professional experience details for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience record that needs to be updated.</param>
    /// <param name="professionalExperienceIto">An object containing the updated details of the professional experience.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>
        public async Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceUpdateCommand(professionalExperienceId, professionalExperienceIto, userId));
        }


    /// <summary>
    /// Remove a specified user's professional experience.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be removed.</param>
    /// <param name="userId">The unique identifier of the user from whom the professional experience will be removed.</param>
        public async Task RemoveUserProfessionalExperienceAsync(int professionalExperienceId, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceDeleteCommand(professionalExperienceId, userId));
        }


    /// <summary>
    /// Replace the latest study information for a specific user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the latest study information is being replaced.</param>
    /// <param name="studyInfos">An object containing the new study information to replace the previous data for the specific user.</param>
        public async Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos)
        {
            await _mediator.Send(new UserLatestStudyInformationsReplaceCommand(studyInfos, userId));
        }


    /// <summary>
    /// Update a user's notification registration by sending a command with their ID, school ID, notification type, and subscription statuses for email and push notifications.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose notification registration is to be updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to be updated.</param>
    /// <param name="isEmailSubscriptionActive">Indicates whether the user's email subscription for the notification type is active. It is an optional parameter.</param>
    /// <param name="isPushSubscriptionActive">Indicates whether the user's push subscription for the notification type is active. It is an optional parameter.</param>
        public async Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive)
        {
            await _mediator.Send(new UserNotificationRegistrationUpdateCommand(userId, schoolId, notificationTypeCode, isEmailSubscriptionActive, isPushSubscriptionActive));
        }


    /// <summary>
    /// Update the first connection date for a specified user using a given date.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose first connection date needs to be updated.</param>
    /// <param name="connectionDateUtc">The date and time of the user's first connection in UTC. If null, the current date and time will be used.</param>
        public async Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDateUtc = null)
        {
            await _mediator.Send(new UserFirstConnectionDateUpdateCommand(userId, connectionDateUtc));
        }


    /// <summary>
    /// Generate a user profile using provided personal details and default settings if certain values are not given.
    /// </summary>
    /// <param name="civilityId">The unique identifier representing the user's civility status (e.g., Mr, Mrs, Dr).</param>
    /// <param name="lastName">The user's family name or surname.</param>
    /// <param name="firstName">The user's given name or first name.</param>
    /// <param name="birthDate">The user's date of birth in the DateOnly format.</param>
    /// <param name="email">The user's email address used for communication and identification.</param>
    /// <param name="pseudo">An optional pseudonym or nickname for the user. Can be null.</param>
    /// <param name="isOfficial">A boolean indicating if the user profile is official.</param>
    /// <param name="isTester">A boolean indicating if the user profile is marked as a tester account.</param>
    /// <param name="maidenName">An optional maiden name for the user. Can be null.</param>
    /// <param name="createBy">The identifier of the entity or user who created the profile.</param>
    /// <returns>Returns a task with the created user profile.</returns>
        public async Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy)
        {
            var civility = _civilityService.GetCivility(civilityId);

            // If pseudo is null then generate it 
            pseudo ??= await _userQueryService.GeneratePseudoAsync(firstName, lastName);

            return await _mediator.Send(new UserProfileCreateCommand(civility!.Name, lastName, firstName, birthDate, email, pseudo!, isOfficial, isTester, _customWebResource.DefaultAvatarUrl, _customWebResource.DefaultHeaderProfileBackgroundUrl, maidenName, createBy));
        }


    /// <summary>
    /// Retrieve comments associated with a given code if the code string is not empty.
    /// </summary>
    /// <param name="code">The code string for which comments are to be retrieved. It should not be empty.</param>
    /// <param name="userReliability">An optional parameter representing a user reliability interface. It provides additional context or permissions related to the retrieval of comments.</param>
    /// <returns>Returns a list of comments from the specified code.</returns>
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
    /// Send a tracking event with relevant data.
    /// </summary>
    /// <param name="userId">The identifier for the user initiating the tracking event.</param>
    /// <param name="title">The title or name of the tracking event.</param>
    /// <param name="comments">Additional comments or information related to the tracking event.</param>
    /// <param name="createBy">The name or ID of the entity creating the tracking event.</param>
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