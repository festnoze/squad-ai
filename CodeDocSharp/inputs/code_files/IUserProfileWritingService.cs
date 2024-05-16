using Microsoft.AspNetCore.Http;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileWriti
    /// <summary>
    /// Verify the reliability of a payment transaction and update the associated status.
    /// </summary>
    /// <param name="salesforceId">The unique identifier for the Salesforce record. This parameter is used to link the user profile data with the corresponding Salesforce record.</param>
    /// <param name="code">A code representing the specific operation or context within which the user profile is being created or updated. This could be an error code, transaction code, etc.</param>
    /// <param name="isCsvUpload">A boolean flag indicating whether the user profile data is being uploaded from a CSV file. When true, it signifies that the data source for user information is a CSV upload.</param>
ngService
    {
        Task UpdatePaymentReliabilityAsync(string salesforceId, string code, boo
    /// <summary>
    /// Upload the payment reliability data from a provided CSV file.
    /// </summary>
    /// <param name="file">The CSV file to be uploaded. This file should contain the data needed for creating user profiles, it should be properly formatted and validated before being processed.</param>
l isCsvUpload);

        Task UploadCsvFilePaymentReliabilityAsync(I
    /// <summary>
    /// Update the review date for a user's profile.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This ID is required to fetch and update the user's profile.</param>
    /// <param name="reviewDate">An optional parameter specifying the date and time when the user's profile review was conducted. If not provided, it defaults to null.</param>
FormFile file);

        Task UpdateUserProfileReviewDateAsync(int userId, DateTime? revi
    /// <summary>
    /// Update a user's profile picture with a new image.
    /// </summary>
    /// <param name="userId">Represents the unique identifier of the user whose profile picture is being updated. This ID is an integer value that uniquely identifies the user within the system.</param>
    /// <param name="fileGuid">Represents the unique identifier of the file containing the new profile picture. This GUID ensures that the specified file is correctly associated with the user's profile update.</param>
ewDate = null);

        Task UpdateProfilePictureAsync(int userId, 
    /// <summary>
    /// Update the header picture for a user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile is being created. This integer value ensures that the user information is correctly linked to the respective data repository entry.</param>
    /// <param name="fileGuid">The globally unique identifier for the file that represents the user's header picture. This Guid ensures that the correct image is associated with the user's profile in the designated data repository.</param>
Guid fileGuid);

        Task UpdateHeaderPictureAsync(int userId, 
    /// <summary>
    /// Update specified user's basic information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile is being updated. This ID is necessary to fetch the correct user data from the repository.</param>
    /// <param name="linkedInUrl">The LinkedIn profile URL of the user. This parameter is optional and may be null if the user does not wish to provide it.</param>
    /// <param name="aboutMe">A brief description about the user. This parameter is optional and can be null if the user does not wish to provide additional information.</param>
Guid fileGuid);

        Task UpdateBasicInfoAsync(int userId, string? linkedInUrl, st
    /// <summary>
    /// Update appearance status in the ranking table for specified entries.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This ID is used to distinguish between different user profiles in the system.</param>
    /// <param name="schoolId">The unique identifier for the school. This ID ensures that the user profile is associated with the correct educational institution.</param>
    /// <param name="doesAppearInRanking">A boolean value indicating whether the user should appear in the ranking. This flag determines if the user's profile will be displayed in the ranking list.</param>
ring? aboutMe);

        Task UpdateDoesAppearInRankingAsync(int userId, int schoolId, bool doesAp
    /// <summary>
    /// Update the visibility status of a specified user in the learner directory based on given parameters.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile is being created or updated.</param>
    /// <param name="schoolId">The unique identifier for the school that the user is associated with.</param>
    /// <param name="doesAppearInLearnerDirectory">A boolean value indicating whether the user should be listed in the learner directory.</param>
    /// <param name="isOpenToCollaboration">A boolean value indicating whether the user is open to collaborating with others.</param>
pearInRanking);

        Task UpdateDoesAppearInLearnerDirectoryAsync(int userId, int schoolId, bool doesAppearInLearnerDirectory, bool isOpenTo
    /// <summary>
    /// Update the current location based on new input data
    /// </summary>
    /// <param name="userId">The unique identifier for the user. It is required to locate the user's profile in the data repository and to ensure that the profile is updated correctly.</param>
    /// <param name="countryCode">An optional parameter representing the user's country code. It assists in location-specific adjustments and validations within the user profile.</param>
    /// <param name="timezoneId">An optional parameter that denotes the user's timezone. This is useful for correctly setting time-related fields and for ensuring the user's profile has accurate temporal data.</param>
Collaboration);

        Task UpdateActualLocationAsync(int userId, string? countryCode, strin
    /// <summary>
    /// Add a professional experience entry to a user's profile, including details such as job title, company, start date, and end date, after validating the provided input for completeness and correctness.
    /// </summary>
    /// <param name="professionalExperience">The professional experience details of the user that need to be added, encapsulated in a ProfessionalExperienceIto object. This includes all necessary information about the user's professional background.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience is being recorded. This ID ensures that the experience is correctly associated with the specific user.</param>
    /// <returns>Returns a task representing the asynchronous operation of adding a professional experience entry.</returns>
g? timezoneId);

        Task<int> AddUserProfessionalExperienceAsync(ProfessionalExperienceIto professionalExperienc
    /// <summary>
    /// Update a user's professional experience details based on provided information.
    /// </summary>
    /// <param name="professionalExperienceId">The unique identifier for the professional experience to be updated. This parameter ensures that the specific professional experience record for the user is correctly identified.</param>
    /// <param name="professionalExperienceIto">An object containing the details of the professional experience to be updated. This includes all relevant information such as job title, company, start date, end date, and other related details.</param>
    /// <param name="userId">The unique identifier for the user whose professional experience is being updated. This ensures that the update is applied to the correct user's profile.</param>
e, int userId);

        Task UpdateUserProfessionalExperienceAsync(int professionalExperienceId, ProfessionalExperienceIto professionalExperienceIt
    /// <summary>
    /// Remove professional experience for a specified user.
    /// </summary>
    /// <param name="id">The unique identifier for the user profile to be created.</param>
    /// <param name="userId">The unique identifier of the user whose professional experience is being removed.</param>
o, int userId);

        Task RemoveUserProfessionalExperienceAsync(int i
    /// <summary>
    /// Replace the most recent study information for a particular instance, ensuring up-to-date data is maintained.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. It is necessary to specify which user's data is being manipulated and validated.</param>
    /// <param name="studyInfos">The information object containing the study details of the user. This includes details that need to be gathered, validated, and stored as part of creating the user's profile.</param>
d, int userId);

        Task ReplaceLatestStudyInformationsAsync(int userId, StudyI
    /// <summary>
    /// Update the registration status of a notification system for a specified entity or user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This is an integer value representing the user in the system.</param>
    /// <param name="schoolId">The unique identifier for the school. This is an integer value representing the school to which the user is associated.</param>
    /// <param name="notificationTypeCode">The code representing the type of notification. This is a string that identifies the category of notifications the user is interested in.</param>
    /// <param name="isEmailSubscriptionActive">A boolean flag indicating whether the email subscription is active. If true, the user will receive notifications via email.</param>
    /// <param name="isPushSubscriptionActive">A boolean flag indicating whether the push notification subscription is active. If true, the user will receive notifications via push notifications.</param>
to studyInfos);

        Task UpdateNotificationRegistration(int userId, int schoolId, string notificationTypeCode, bool? isEmailSubscriptionActive, bool? isPushSubsc
    /// <summary>
    /// Update the first connection date for a user if it is their initial login.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This is an integer value that is required to locate and update the user's profile in the data repository.</param>
    /// <param name="connectionDate">The date and time of the user's first connection. This is an optional parameter represented as a nullable DateTime. If not provided, it defaults to null.</param>
riptionActive);

        Task UpdateUserFirstConnectionDateAsync(int userId, DateTime? connecti
    /// <summary>
    /// Create a user profile, ensuring that all required user information is gathered, validated, and stored in the designated data repository.
    /// </summary>
    /// <param name="civilityId">An integer representing the civility ID, used to address the user's title like Mr., Mrs., etc.</param>
    /// <param name="lastName">The last name of the user, a string that includes the user's family name.</param>
    /// <param name="firstName">The first name of the user, a string that includes the user's given name.</param>
    /// <param name="birthDate">The birth date of the user, formatted as a DateOnly, which includes the user's date of birth excluding time.</param>
    /// <param name="email">The email address of the user, a string used for communication and authentication.</param>
    /// <param name="pseudo">An optional string representing the user's pseudonym or nickname, which may be null.</param>
    /// <param name="isOfficial">A boolean indicating whether the user is an official representative or has some formal status.</param>
    /// <param name="isTester">A boolean indicating whether the user is involved in testing activities.</param>
    /// <param name="maidenName">An optional string representing the user's maiden name, which may be null. Typically used for female users.</param>
    /// <param name="createBy">A string representing who created the profile, usually the username or ID of the profile creator.</param>
    /// <returns>Returns a Task containing the new user profile information.</returns>
onDate = null);

        Task<int> CreateUserProfileAsync(int civilityId, string lastName, string firstName, DateOnly birthDate, string email, string? pseudo, bool isOfficial, bool isTester, string? maidenName, string createBy);
    }
}