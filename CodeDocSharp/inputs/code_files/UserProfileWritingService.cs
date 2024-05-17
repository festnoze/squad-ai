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
    /// Initialize the mediator, tracking client, logger, and user repository with provided instances, ensuring the mediator is not null.
    /// </summary>
    /// <param name="mediator">The mediator instance used for handling and dispatching requests. It is essential that this is not null.</param>
    /// <param name="customWebResource">The custom web resource service instance used for accessing and managing web resources.</param>
    /// <param name="civilityService">The civility service instance used for handling operations related to user civility details.</param>
    /// <param name="userQueryService">The user profile querying service instance used for querying user profiles.</param>
    /// <param name="trackingClient">The tracking client instance used for tracking and logging user activity.</param>
    /// <param name="logger">The logger instance provided for logging operations specifically related to the UserProfileWritingService class.</param>
    /// <param name="userRepository">The user repository instance used for performing CRUD operations on user data.</param>
        public UserProfileWritingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserProfileQueryingService userQueryService, ITrackingRestClient trackingClient, ILogger<IUserProfileWritingService> logger, IUserRepository userRepository)
        {
            _mediator = mediator ?? throw new ArgumentNullException();
            _trackingClient = trackingClient;
            _logger = logger;
            _userRepository = userRepository;
        }


    /// <summary>
    /// Attempt to upload a payment reliability data in CSV format.
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
    /// Update the reliability status of a payment using a specific Salesforce ID as a reference. Ensure the provided Salesforce ID is valid, retrieve the associated user ID, and proceed if a valid user ID is found.
    /// </summary>
    /// <param name="salesforceId">The Salesforce ID used to identify and update the reliability status of a payment. Ensure the provided Salesforce ID is valid.</param>
    /// <param name="code">A unique code associated with the payment process. This code is necessary for identifying the specific action to be taken on the payment.</param>
    /// <param name="isCsvUpload">A boolean flag indicating whether the payment update is being performed via a CSV upload. Set to true if the update is from a CSV file, otherwise false.</param>
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
    /// Update the review date of a user's profile based on the provided user ID and review date.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile review date needs to be updated.</param>
    /// <param name="reviewDateUtc">The updated review date of the user's profile in UTC. If null, the current date and time will be used.</param>
        public async Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDateUtc = null)
        {
            await _mediator.Send(new UserProfileReviewDateUpdateCommand(userId, reviewDateUtc));
        }


    /// <summary>
    /// Update a user's profile picture using a given file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile picture is to be updated.</param>
    /// <param name="fileGuid">The unique file identifier for the new profile picture to be set.</param>
        public async Task UpdateProfilePictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserProfilePictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update the header picture for a specified user with the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose header picture is to be updated.</param>
    /// <param name="fileGuid">The unique identifier of the file that contains the new header picture.</param>
        public async Task UpdateHeaderPictureAsync(int userId, Guid fileGuid)
        {
            await _mediator.Send(new UserHeaderPictureUpdateCommand(userId, fileGuid));
        }


    /// <summary>
    /// Update basic information for a user with provided LinkedIn URL and description.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose basic information needs to be updated.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional and can be null.</param>
    /// <param name="aboutMe">A brief description or biography about the user. This parameter is optional and can be null.</param>
        public async Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe)
        {
            await _mediator.Send(new UserBasicInfoUpdateCommand(userId, linkedInUrl, aboutMe));
        }


    /// <summary>
    /// Update the ranking status for a specified user in a particular school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose ranking status is to be updated.</param>
    /// <param name="schoolId">The unique identifier for the school in which the user's ranking status is to be updated.</param>
    /// <param name="doesAppearInRanking">A boolean flag indicating whether the user should appear in the ranking (true) or not (false).</param>
        public async Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking)
        {
            await _mediator.Send(new UserAppearsInRankingUpdateCommand(userId, schoolId, doesAppearInRanking));
        }


    /// <summary>
    /// Update the learner directory status for a specified user to reflect visibility and collaboration settings.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose learner directory status is being updated.</param>
    /// <param name="schoolId">The unique identifier of the school to which the user belongs.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean indicating whether the user should appear in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean indicating whether the user is open to collaboration with other learners.</param>
        public async Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration)
        {
            await _mediator.Send(new UserAppearsInLearnerDirectoryUpdateCommand(userId, schoolId, doesAppearInLearnerDirectory, isOpenToCollaboration));
        }


    /// <summary>
    /// Update the current location details for a specified user, including country and timezone information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose location details are being updated.</param>
    /// <param name="countryCode">The code representing the country for the user's current location. It can be null if the country is not specified.</param>
    /// <param name="timezoneId">The identifier for the timezone of the user's current location. It can be null if the timezone is not specified.</param>
        public async Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId)
        {
            await _mediator.Send(new UserActualLocationUpdateCommand(userId, countryCode, timezoneId));
        }


    /// <summary>
    /// Add a new professional experience for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">An instance containing the professional experience information to be added for the specified user.</param>
    /// <param name="userId">The unique identifier of the user for whom the professional experience is being added.</param>
    /// <returns>Returns a Task representing the asynchronous operation.</returns>
        public async Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            return await _mediator.Send(new UserProfessionalExperienceCreateCommand(professionalExperienceIto, userId));
        }


    /// <summary>
    /// Update a user's professional experience based on provided details.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience entry to be updated.</param>
    /// <param name="professionalExperienceIto">An object containing the new details of the professional experience to update.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>
        public async Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceUpdateCommand(professionalExperienceId, professionalExperienceIto, userId));
        }


    /// <summary>
    /// Remove a specified professional experience for a user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be removed.</param>
    /// <param name="userId">The unique identifier of the user from whom the professional experience will be removed.</param>
        public async Task RemoveUserProfessionalExperienceAsync(int professionalExperienceId, int userId)
        {
            await _mediator.Send(new UserProfessionalExperienceDeleteCommand(professionalExperienceId, userId));
        }


    /// <summary>
    /// Replace the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose study information is to be replaced.</param>
    /// <param name="studyInfos">The new study information that will replace the existing information for the specified user.</param>
        public async Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos)
        {
            await _mediator.Send(new UserLatestStudyInformationsReplaceCommand(studyInfos, userId));
        }


    /// <summary>
    /// Update notification registration for a specified user based on provided parameters.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the notification registration is to be updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to be updated (e.g., email, push).</param>
    /// <param name="isEmailSubscriptionActive">A nullable boolean indicating whether the email subscription is active. If null, no changes will be made.</param>
    /// <param name="isPushSubscriptionActive">A nullable boolean indicating whether the push subscription is active. If null, no changes will be made.</param>
        public async Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive)
        {
            await _mediator.Send(new UserNotificationRegistrationUpdateCommand(userId, schoolId, notificationTypeCode, isEmailSubscriptionActive, isPushSubscriptionActive));
        }


    /// <summary>
    /// Update the first connection date for a specified user using the UTC date provided.
    /// </summary>
    /// <param name="userId">An integer representing the ID of the user whose first connection date is to be updated.</param>
    /// <param name="connectionDateUtc">An optional DateTime representing the UTC date of the user's first connection. If not provided, the current date and time may be used.</param>
        public async Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDateUtc = null)
        {
            await _mediator.Send(new UserFirstConnectionDateUpdateCommand(userId, connectionDateUtc));
        }


    /// <summary>
    /// Create a user profile by fetching necessary details including civility, pseudo, and other personal information, and then sending a command to create the profile with default avatar and background URLs.
    /// </summary>
    /// <param name="civilityId">An integer representing the user's civility identifier.</param>
    /// <param name="lastName">A string representing the user's last name.</param>
    /// <param name="firstName">A string representing the user's first name.</param>
    /// <param name="birthDate">A DateOnly object representing the user's date of birth.</param>
    /// <param name="email">A string representing the user's email address.</param>
    /// <param name="pseudo">An optional string representing the user's pseudonym or nickname.</param>
    /// <param name="isOfficial">A boolean indicating if the user is an official.</param>
    /// <param name="isTester">A boolean indicating if the user is a tester.</param>
    /// <param name="maidenName">An optional string representing the user's maiden name.</param>
    /// <param name="createBy">A string identifying who created the user profile.</param>
    /// <returns>Returns a Task representing the asynchronous creation of a user profile.</returns>
        public async Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy)
        {
            var civility = _civilityService.GetCivility(civilityId);

            // If pseudo is null then generate it 
            pseudo ??= await _userQueryService.GeneratePseudoAsync(firstName, lastName);

            return await _mediator.Send(new UserProfileCreateCommand(civility!.Name, lastName, firstName, birthDate, email, pseudo!, isOfficial, isTester, _customWebResource.DefaultAvatarUrl, _customWebResource.DefaultHeaderProfileBackgroundUrl, maidenName, createBy));
        }


    /// <summary>
    /// Retrieve comments embedded within a provided code snippet if the code is non-empty.
    /// </summary>
    /// <param name="code">The code snippet from which comments need to be retrieved. It should be a non-empty string to perform the extraction.</param>
    /// <param name="userReliability">An optional UserReliabilityIto object that provides additional context or configuration for the comment retrieval process based on user reliability parameters.</param>
    /// <returns>Returns comments extracted from the provided non-empty code snippet.</returns>
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
    /// Track a specified event and send the tracking information to a predefined endpoint, handling any possible exceptions during the process.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user who performed the event.</param>
    /// <param name="title">A string containing the title or name of the event being tracked.</param>
    /// <param name="comments">A string for any additional comments or details about the event.</param>
    /// <param name="createBy">A string indicating who created or initiated the tracking event.</param>
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