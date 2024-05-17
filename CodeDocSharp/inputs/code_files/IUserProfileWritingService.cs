using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWritingService
    {

    /// <summary>
    /// Update the payment reliability for a given user based on their Salesforce ID.
    /// </summary>
    /// <param name="salesforceId">The Salesforce identifier used to associate the payment reliability update with the correct record in Salesforce.</param>
    /// <param name="code">A unique code representing the specific operation or transaction for which the payment reliability is being updated.</param>
    /// <param name="isCsvUpload">Indicates whether the payment reliability update is being uploaded via a CSV file.</param>
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, bool isCsvUpload);

    /// <summary>
    /// Upload the contents of a CSV file containing payment reliability data to a designated storage or processing system.
    /// </summary>
    /// <param name="file">The IFormFile representing the CSV file to be uploaded</param>

        Task UploadCsvFilePaymentReliabilityAsync(IFormFile file);

    /// <summary>
    /// Update the review date of the user profile with the specified user ID and UTC review date.
    /// </summary>
    /// <param name="userId">The unique identifier of the user to be analyzed or updated.</param>
    /// <param name="reviewDateUtc">The date and time of the review in UTC. If not provided, defaults to null.</param>

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? reviewDate = null);

    /// <summary>
    /// Update the profile picture for a specified user using the provided file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile picture is to be updated.</param>
    /// <param name="fileGuid">The unique identifier of the file that will be used to update the user's profile picture.</param>

        Task UpdateProfilePictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update the header picture for a specified user using a unique file identifier.
    /// </summary>
    /// <param name="userId">The unique identifier for a user to update the header picture.</param>
    /// <param name="fileGuid">The unique identifier for the file representing the new header picture.</param>

        Task UpdateHeaderPictureAsync(int userId, Guid fileGuid);

    /// <summary>
    /// Update basic information for a specified user by sending a command with user ID, LinkedIn URL, and about me details.
    /// </summary>
    /// <param name="userId">The unique identifier for a user.</param>
    /// <param name="linkedInUrl">The optional LinkedIn profile URL for the user.</param>
    /// <param name="aboutMe">The optional personal information or biography for the user.</param>

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, string? aboutMe);

    /// <summary>
    /// Update a user's ranking appearance status based on specified conditions.
    /// </summary>
    /// <param name="userId">The unique identifier of a user.</param>
    /// <param name="schoolId">The unique identifier of a school.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether it appears in the ranking.</param>

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAppearInRanking);

    /// <summary>
    /// Update the learner directory status for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user.</param>
    /// <param name="schoolId">The unique identifier of the school.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean value indicating whether the user appears in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean value indicating whether the user is open to collaboration.</param>

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenToCollaboration);

    /// <summary>
    /// Update the actual location of a specified user with new country and timezone data.
    /// </summary>
    /// <param name="userId">The identifier for the user for whom the location is being updated.</param>
    /// <param name="countryCode">The code representing the user's country, which is optional.</param>
    /// <param name="timezoneId">The identifier for the user's timezone, which is optional.</param>

        Task UpdateActualLocationAsync(int userId, string? countryCode, string? timezoneId);

    /// <summary>
    /// Add a professional experience entry for a specified user.
    /// </summary>
    /// <param name="professionalExperienceIto">The professional experience information object that holds the details of the user's professional experience.</param>
    /// <param name="userId">The unique identifier of the user to whom the professional experience is being added.</param>
    /// <returns>Returns a task indicating the completion of the professional experience addition.</returns>

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperience, int userId);

    /// <summary>
    /// Update professional experience details for a specified user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience being updated.</param>
    /// <param name="professionalExperienceIto">The data transfer object containing the updated details of the professional experience.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience is being updated.</param>

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIto, int userId);

    /// <summary>
    /// Remove a specified professional experience for a given user.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier of the professional experience record to be removed.</param>
    /// <param name="userId">The unique identifier of the user associated with the professional experience.</param>

        Task RemoveUserProfessionalExperienceAsync(int id, int userId);

    /// <summary>
    /// Update the latest study information for a specified user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user.</param>
    /// <param name="studyInfos">An object of type StudyIto containing the information related to the study.</param>

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyIto studyInfos);

    /// <summary>
    /// Update notification registration details for a user, considering their school ID, notification type, and preferences for email and push subscriptions.
    /// </summary>
    /// <param name="userId">The identifier of the user</param>
    /// <param name="schoolId">The identifier of the school</param>
    /// <param name="notificationTypeCode">The code representing the type of notification</param>
    /// <param name="isEmailSubscriptionActive">Indicates whether the email subscription is active</param>
    /// <param name="isPushSubscriptionActive">Indicates whether the push subscription is active</param>

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubscriptionActive);

    /// <summary>
    /// Update the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user</param>
    /// <param name="connectionDateUtc">The optional UTC date and time of the user's connection; defaults to null if not provided</param>

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connectionDate = null);

    /// <summary>
    /// Create a new user profile with generated pseudo if not provided, including personal details, official status, tester status, and default resources.
    /// </summary>
    /// <param name="civilityId">The unique identifier representing the individual's civility title.</param>
    /// <param name="lastName">The surname of the user.</param>
    /// <param name="firstName">The given name of the user.</param>
    /// <param name="birthDate">The birth date of the user.</param>
    /// <param name="email">The email address of the user.</param>
    /// <param name="pseudo">The optional pseudonym of the user.</param>
    /// <param name="isOfficial">Determines if the user is an official member.</param>
    /// <param name="isTester">Determines if the user is a tester.</param>
    /// <param name="maidenName">The optional maiden name of the user.</param>
    /// <param name="createBy">The identifier of the entity that created the user profile.</param>
    /// <returns>Returns a Task containing the newly created user profile object.</returns>

        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}