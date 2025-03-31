using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.Text.Json.Serialization;

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Gender { M, Mme, Dr, Autre }

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Country
{
    AF, AL, DZ, DE, AD, AO, AI, AQ, AG, AR, AM, AW, AU, AT, AZ, BS, BH, BD, BB, BY, BE, BZ, BJ, BM, BT, BO, BQ, BA, BW, BR, BN, BG, BF, BI, KY, KH, CM, CA, CV, CF, CL, CN, CY, CO, KM, CG, CD, KP, KR, CR, CI, HR, CU, CW, DK, DJ, DM, EG, AE, EC, ER, ES, EE, ET, FJ, FI, FR, GA, GM, GE, GS, GH, GI, GR, GD, GL, GP, GU, GT, GG, GN, GW, GQ, GY, GF, HT, HN, HU, BV, IM, NF, NG, NI, NL, NO, NP, NR, NU, NZ, OM, PA, PE, PF, PG, PH, PK, PL, PM, PN, PR, PT, PW, PY, QA, RE, RO, RS, RU, RW, SA, SB, SC, SD, SE, SG, SH, SI, SJ, SK, SL, SM, SN, SO, SR, SS, ST, SV, SX, SY, SZ, TC, TD, TF, TG, TH, TJ, TK, TL, TM, TN, TO, TR, TT, TV, TZ, UA, UG, UM, US, UY, UZ, VA, VC, VE, VG, VI, VN, VU, WF, WS, YE, YT, ZA, ZM, ZW, AX, AS, IO, CX, CC, CK, CZ, DO, FK, FO, HM, HK, IS, IN, ID, IR, IQ, IE, IL, IT, JM, JP, JE, JO, KZ, KE, KI, KW, KG, LA, LV, LB, LS, LR, LY, LI, LT, LU, MO, MG, MW, MY, MV, ML, MT, MH, MQ, MR, MU, MX, FM, MD, MC, MN, ME, MS, MA, MZ, MM, NC, NE, MP, PS, BL, KN, LC, MF, LK, CH, TW, GB, EH
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum DeviceType { CORE_PKL_Computer, CORE_PKL_Phone, CORE_PKL_Tablet }

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum UtmMedium
{
    CORE_PKL_Directory,
    CORE_PKL_Bot,
    CORE_PKL_Cpc,
    CORE_PKL_Display,
    CORE_PKL_Email,
    CORE_PKL_PDF,
    CORE_PKL_Organic,
    CORE_PKL_PT,
    CORE_PKL_Referral,
    CORE_PKL_Site,
    CORE_PKL_Smo,
    CORE_PKL_Sms,
    CORE_PKL_None,
    CORE_PKL_Affiliate,
    CORE_PKL_Print,
    CORE_PKL_Unknown,
    CORE_PKL_Remarketing,
    CORE_PKL_SMA,
    IT_PKL_AutoreplyLinks,
    IT_PKL_Fair,
    IT_PKL_ADVBA,
    IT_PKL_SchoolForum,
    IT_PKL_internalEmail,
    CORE_PKL_SEA,
    CORE_PKL_Perfmax,
    CORE_PKL_Video,
    STUDI_PKL_Import,
    STUDI_PKL_Whatsapp
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Funding
{
    CORE_PKL_Contrat_individuel,
    CORE_PKL_CPF,
    CORE_PKL_CPF_abonde,
    STUDI_PKL_CPF_Public,
    CORE_PKL_CPF_de_transition,
    CORE_PKL_AIF,
    CORE_PKL_SAS_Apprentissage,
    CORE_PKL_AO_Pole_emploi,
    CORE_PKL_SAFIR_IDF,
    CORE_PKL_FNE_Chomage,
    CORE_PKL_Contrat_de_professionnalisation,
    CORE_PKL_ProA,
    CORE_PKL_Apprentissage,
    CORE_PKL_Plan_de_Developpement_des_Competences,
    CORE_PKL_Contrat_de_reclassement,
    STUDI_PKL_AIRE2,
    STUDI_PKL_PRF_IDF
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum CaptureChannel { CORE_PKL_Phone_call, CORE_PKL_Application_Online, CORE_PKL_Web_form }

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum FormType
{
    CORE_PKL_Online_Shop,
    CORE_PKL_Application_file,
    CORE_PKL_Application_online,
    CORE_PKL_Examination,
    CORE_PKL_Contact,
    CORE_PKL_Booking_appointment,
    CORE_PKL_Preparation_Day_Mock_Competition,
    CORE_PKL_Funding,
    CORE_PKL_Registration,
    CORE_PKL_Open_day,
    CORE_PKL_Call_back,
    CORE_PKL_Fairs,
    CORE_PKL_Admission_session,
    CORE_PKL_Surqualification,
    CORE_PKL_Virtual_open_day,
    CORE_PKL_Webinar,
    CORE_PKL_Scholarship,
    CORE_PKL_Trial_Period,
    CORE_PKL_Sponsorship
}

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum FormArea { CORE_PKL_Bottom_of_page, CORE_PKL_Thank_you_page, CORE_PKL_Content, CORE_PKL_Embeded, CORE_PKL_Footer, CORE_PKL_Header, CORE_PKL_Interstitial, CORE_PKL_Page, CORE_PKL_Sidebar }

[JsonConverter(typeof(JsonStringEnumConverter))]
public enum Alternance { Oui, Non }

public class LIDForm
{
    [Required]
    public Identity Identity { get; set; } = new();
    [Required]
    public Address Address { get; set; } = new();
    [Required]
    public ContactInfo ContactInfo { get; set; } = new();
    [Required]
    public TechnicalInfo TechnicalInfo { get; set; } = new();
    [Required]
    public Utm Utm { get; set; } = new();
    [Required]
    public Additional Additional { get; set; } = new();
}

public class Identity
{
    [Required, MinLength(1), MaxLength(100)]
    public string Nom { get; set; } = string.Empty;
    [Required, MinLength(1), MaxLength(100)]
    public string Prenom { get; set; } = string.Empty;
    public Gender? Gender { get; set; }
    public DateTime? Birthdate { get; set; }
    [Range(1900, 2100)]
    public int? Birthyear { get; set; }
    [MinLength(1), MaxLength(100)]
    public string? ProfessionalSituation { get; set; }
    [MinLength(1), MaxLength(100)]
    public string? DiplomaLevel { get; set; }
    [MinLength(1), MaxLength(100)]
    public string? DiplomaName { get; set; }
}

public class Address
{
    [Required, MinLength(1), MaxLength(200)]
    public string Street { get; set; } = string.Empty;
    [Required, MinLength(4), MaxLength(10)]
    public string PostalCode { get; set; } = string.Empty;
    [Required, MinLength(1), MaxLength(100)]
    public string City { get; set; } = string.Empty;
    public Country Pays { get; set; } = Country.FR;
}

public class ContactInfo
{
    [Required, MinLength(5), MaxLength(100)]
    public string Email { get; set; } = string.Empty;
    [Required, MinLength(8), MaxLength(20)]
    public string Telephone { get; set; } = string.Empty;
}

public class TechnicalInfo
{
    [Required, MinLength(5), MaxLength(200)]
    public string Url { get; set; } = string.Empty;
    [MinLength(7), MaxLength(15)]
    public string? IpAddress { get; set; }
    public DeviceType? Device { get; set; }
    public DateTime? FirstVisit { get; set; }
    [MinLength(1), MaxLength(200)]
    public string? FirstPage { get; set; }
}

public class Utm
{
    [Required, MinLength(1), MaxLength(100)]
    public string UtmSource { get; set; } = string.Empty;
    public UtmMedium UtmMedium { get; set; }
    [MinLength(1), MaxLength(100)]
    public string? UtmCampaign { get; set; }
    [MinLength(1), MaxLength(100)]
    public string? UtmContent { get; set; }
    [MinLength(1), MaxLength(100)]
    public string? UtmTerm { get; set; }
}

public class Additional
{
    [MaxLength(100)]
    public string? Thematique { get; set; }
    [Required, MinLength(1), MaxLength(100)]
    public string Formulaire { get; set; } = string.Empty;
    [MinLength(1), MaxLength(500)]
    public string? Consentement { get; set; }
    [MinLength(5), MaxLength(200)]
    public string? DocumentUrl { get; set; }
    public Funding? Funding { get; set; }
    public CaptureChannel? CaptureChannel { get; set; }
    public FormType? FormType { get; set; }
    public FormArea? FormArea { get; set; }
    [MaxLength(500)]
    public string? FormMoreInformation { get; set; }
    [MaxLength(500)]
    public string? Comments { get; set; }
    [MinLength(1), MaxLength(100)]
    public string? TrainingCourseId { get; set; }
    public Alternance Alternance { get; set; } = Alternance.Non;
    [MinLength(1), MaxLength(100)]
    public string? TechSource { get; set; }
    public string? Cv { get; set; }
}
