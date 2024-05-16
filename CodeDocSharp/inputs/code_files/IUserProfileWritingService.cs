using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWritingService
    {

    /// <summary>
    /// Update the reliability status of a payment based on the provided Salesforce ID, ensuring the ID is not null or empty and retrieving the corresponding user ID for further validation.
    /// </summary>
    /// <param name="salesforceId">The unique identifier associated with the Salesforce record. This parameter is used to identify the specific record within Salesforce to update.</param>
    /// <param name="code">The code associated with the payment reliability update. This parameter specifies the type or category of the update being sent.</param>
    /// <param name="isCsvUpload">A boolean value that indicates whether the data is being uploaded in CSV format. True if uploading CSV data, otherwise false.</param>
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload);

    /// <summary>
    /// Analyze the content of a CSV file related to payment reliability, ensure data validation, and upload it to the server logging any issues encountered.
    /// </summary>
    /// <param name="file">The CSV file containing the tracking information that needs to be uploaded.</param>

        Task UploadCsvFilePaymentReliabilityAsync(IFormFile file);

    /// <summary>
    /// Update the review date of a user's profile to a specified timestamp.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the profile review date is to be updated. This parameter is mandatory.</param>
    /// <param name="reviewDateUtc">The date and time of the review in UTC. This parameter is optional and defaults to null if not provided.</param>

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDate = null);

    /// <summary>
    /// Update the profile picture for a specified user using the provided file identifier.
    /// </summary>
    /// <param name="userId">An integer representing the unique user identifier for whom the profile picture is being updated.</param>
    /// <param name="fileGuid">A globally unique identifier (GUID) representing the file associated with the user's profile picture.</param>

        Task UpdateProfilePictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the header picture for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose header picture is to be updated.</param>
    /// <param name="fileGuid">The unique identifier (GUID) of the file representing the new header picture.</param>

        Task UpdateHeaderPictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update basic information for a specified user based on given parameters.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This is an integer value.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This is a nullable string value.</param>
    /// <param name="aboutMe">A brief description or bio about the user. This is a nullable string value.</param>

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe);

    /// <summary>
    /// Update user ranking status based on provided user ID, school ID, and appearance indicator.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This is used to specify the user whose tracking information is being updated.</param>
    /// <param name="schoolId">The unique identifier for the school. This parameter helps in identifying the school associated with the user.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether the user appears in the ranking. True if the user appears in the ranking, false otherwise.</param>

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking);

    /// <summary>
    /// Update the user's appearance in the learner directory based on specified parameters.
    /// </summary>
    /// <param name="userId">The unique identifier for the user.</param>
    /// <param name="schoolId">The unique identifier for the school.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean flag indicating whether the user should appear in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean flag indicating whether the user is open to collaboration.</param>

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration);

    /// <summary>
    /// Update the actual location for a specified user, including country and timezone details.
    /// </summary>
    /// <param name="userId">The identifier for the user. This value is required to specify which user's location is being updated.</param>
    /// <param name="countryCode">An optional parameter representing the country code. This can be used to tailor the location update based on regional settings.</param>
    /// <param name="timezoneId">An optional parameter representing the timezone ID. This assists in adjusting the tracking information to the correct time zone context.</param>

        Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId);

    /// <summary>
    /// Add a professional experience for a specified user using a command to handle the operation.
    /// </summary>
    /// <param name="professionalExperienceIto">An object that contains the professional experience details of the user, including fields like company, role, duration, and other relevant information.</param>
    /// <param name="userId">The unique identifier of the user to whom the professional experience details will be associated.</param>
    /// <returns>Returns a task indicating the operation's success status.</returns>

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperience, int userId);

    /// <summary>
    /// Update a user's professional experience.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience entry that needs to be updated.</param>
    /// <param name="professionalExperienceIto">An object containing the details and information of the professional experience to be updated.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience is being updated.</param>

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId);

    /// <summary>
    /// Delete a specified user's professional experience by providing the professional experience ID and user ID.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience to be removed.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience is to be removed.</param>

        Task RemoveUserProfessionalExperienceAsync(int id, int userId);

    /// <summary>
    /// Update the most recent study information for a specific user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user.</param>
    /// <param name="studyInfos">An object of type StudyIto containing detailed study information relevant to the user.</param>

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos);

    /// <summary>
    /// Update the notification registration settings for a specified user based on user ID, school ID, notification type, and subscription status for email and push notifications.
    /// </summary>
    /// <param name="userId">The unique identifier for the user for whom the notification settings are being updated.</param>
    /// <param name="schoolId">The identifier for the school associated with the user.</param>
    /// <param name="notificationTypeCode">A code that specifies the type of notification to be tracked and updated.</param>
    /// <param name="isEmailSubscriptionActive">Indicates whether the email subscription for notifications is active. This is an optional parameter.</param>
    /// <param name="isPushSubscriptionActive">Indicates whether the push subscription for notifications is active. This is an optional parameter.</param>

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive);

    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose connection date is being updated.</param>
    /// <param name="connectionDateUtc">An optional DateTime value representing the UTC date and time of the user's first connection. If not provided, defaults to null.</param>

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDate = null);

    /// <summary>
    /// Create a user profile with specified personal and optional details, ensuring pseudo generation if not provided.
    /// </summary>
    /// <param name="civilityId">A unique identifier representing the civility (e.g., Mr., Mrs., Ms., etc.) of the user.</param>
    /// <param name="lastName">The last name of the user.</param>
    /// <param name="firstName">The first name of the user.</param>
    /// <param name="birthDate">The birth date of the user.</param>
    /// <param name="email">The user's email address.</param>
    /// <param name="pseudo">The user's optional pseudonym or nickname. Can be null.</param>
    /// <param name="isOfficial">A boolean indicating if the profile is official.</param>
    /// <param name="isTester">A boolean indicating if the user is a beta tester.</param>
    /// <param name="maidenName">The maiden name of the user, if applicable. Can be null.</param>
    /// <param name="createBy">The identifier of the entity or user who created the profile.</param>
    /// <returns>Returns the newly created user profile.</returns>

        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}