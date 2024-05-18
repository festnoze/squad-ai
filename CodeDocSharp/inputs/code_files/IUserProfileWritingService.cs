using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWritingService
    {

    /// <summary>
    /// Update the payment reliability status based on the specified Salesforce ID after ensuring the ID is neither null nor empty and retrieving the corresponding user ID.
    /// </summary>
    /// <param name="salesforceId">The Salesforce ID used to identify the specific record. The method ensures that this ID is neither null nor empty before proceeding.</param>
    /// <param name="code">A specific code associated with the payment reliability update. This might be related to a status or result code.</param>
    /// <param name="isCsvUpload">A boolean value indicating whether the update is based on a CSV upload. Helps in determining the source of the update.</param>
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload);

    /// <summary>
    /// Upload a CSV file containing payment reliability data.
    /// </summary>
    /// <param name="file">The CSV file that contains the payment reliability data to be uploaded.</param>

        Task UploadCsvFilePaymentReliabilityAsync(IFormFile file);

    /// <summary>
    /// Update the review date of a user profile using the specified UTC date and user ID.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile review date will be updated.</param>
    /// <param name="reviewDateUtc">The UTC date to set as the review date for the user's profile. If null, no date will be updated.</param>

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDate = null);

    /// <summary>
    /// Update the profile picture for a specified user by sending a corresponding command.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile picture is to be updated.</param>
    /// <param name="fileGuid">The globally unique identifier of the file that contains the new profile picture.</param>

        Task UpdateProfilePictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the header picture for a specified user based on a provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose header picture is to be updated.</param>
    /// <param name="fileGuid">The GUID representing the file to be used as the new header picture.</param>

        Task UpdateHeaderPictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the basic information of a user with specified details including LinkedIn URL and a short description.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose basic information is to be updated.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional.</param>
    /// <param name="aboutMe">The short description or bio of the user. This parameter is optional.</param>

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe);

    /// <summary>
    /// Update a user's ranking status within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose ranking status is being updated.</param>
    /// <param name="schoolId">The unique identifier for the school where the user's ranking status will be updated.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether the user appears in the ranking or not.</param>

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking);

    /// <summary>
    /// Update the learner directory status of a specified user with the provided parameters.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose learner directory status is to be updated.</param>
    /// <param name="schoolId">The identifier of the school associated with the user.</param>
    /// <param name="doesAppearInLearnerDirectory">Specifies whether the user should appear in the learner directory.</param>
    /// <param name="isOpenToCollaboration">Indicates if the user is open to collaboration with others.</param>

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration);

    /// <summary>
    /// Update the current location information for a specified user, including country code and timezone ID.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose location information is being updated.</param>
    /// <param name="countryCode">The country code representing the user's current country. This parameter is optional.</param>
    /// <param name="timezoneId">The timezone ID representing the user's current timezone. This parameter is optional.</param>

        Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId);

    /// <summary>
    /// Add a professional experience entry for a specific user.
    /// </summary>
    /// <param name="professionalExperienceIto">The professional experience information to be added for the user.</param>
    /// <param name="userId">The unique identifier of the user for whom the professional experience is being added.</param>
    /// <returns>Returns a task representing the asynchronous operation.</returns>

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperience, int userId);

    /// <summary>
    /// Update the professional experience details for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience record that needs to be updated.</param>
    /// <param name="professionalExperienceIto">An object containing the updated details of the professional experience.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being updated.</param>

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId);

    /// <summary>
    /// Remove a specified user's professional experience.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience to be removed.</param>
    /// <param name="userId">The unique identifier of the user from whom the professional experience will be removed.</param>

        Task RemoveUserProfessionalExperienceAsync(int id, int userId);

    /// <summary>
    /// Replace the latest study information for a specific user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the latest study information is being replaced.</param>
    /// <param name="studyInfos">An object containing the new study information to replace the previous data for the specific user.</param>

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos);

    /// <summary>
    /// Update a user's notification registration by sending a command with their ID, school ID, notification type, and subscription statuses for email and push notifications.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose notification registration is to be updated.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification to be updated.</param>
    /// <param name="isEmailSubscriptionActive">Indicates whether the user's email subscription for the notification type is active. It is an optional parameter.</param>
    /// <param name="isPushSubscriptionActive">Indicates whether the user's push subscription for the notification type is active. It is an optional parameter.</param>

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive);

    /// <summary>
    /// Update the first connection date for a specified user using a given date.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose first connection date needs to be updated.</param>
    /// <param name="connectionDateUtc">The date and time of the user's first connection in UTC. If null, the current date and time will be used.</param>

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDate = null);

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

        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}