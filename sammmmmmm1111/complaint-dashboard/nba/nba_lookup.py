[
  {
    "major_issue": "UPI",
    "sub_issue": "Amount Debited but Payment Failed",
    "investigation_steps": [
      "Retrieve the transaction reference ID and check NPCI switch logs for the payment status.",
      "Verify if the debit was posted on the core banking system (CBS) while the NPCI response returned failure.",
      "Check if a credit reversal was auto-initiated by the acquiring bank within the stipulated T+1 timeline.",
      "Confirm whether the beneficiary bank received and rejected the credit instruction.",
      "Review UPI transaction state machine logs for the exact failure reason code."
    ],
    "next_best_actions": [
      "If auto-reversal has not been triggered, initiate a manual credit reversal to the customer's account within RBI mandated timelines.",
      "Raise a dispute ticket with NPCI via the bank's dispute management portal if the amount is stuck in transit.",
      "Update the internal CRM with transaction details and assign to the reconciliation desk for follow-up.",
      "Notify the operations team to monitor the reversal settlement in the next NPCI settlement cycle.",
      "Escalate to the UPI Ops team if the reversal is not reflected within 48 hours."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Registration Failed",
    "investigation_steps": [
      "Check the UPI onboarding logs for the specific error code returned during registration.",
      "Verify if the customer's mobile number is correctly mapped to their bank account in CBS.",
      "Confirm that the VPA (Virtual Payment Address) requested is not already in use.",
      "Check if NPCI's UPI mapper has the customer's mobile number linked to the bank account.",
      "Review if there are any KYC or account-level restrictions preventing UPI registration."
    ],
    "next_best_actions": [
      "If the mobile number is not mapped, coordinate with the branch/operations team to update the mobile number in CBS.",
      "Re-trigger the UPI registration request from the bank's UPI switch after resolving the root cause.",
      "If VPA conflict exists, suggest alternative VPA formats to the operations team for manual registration.",
      "Escalate to the UPI technical team if error codes indicate a platform-level issue.",
      "Log the incident in the UPI issue tracker for pattern analysis if multiple registrations are failing."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Bank Account Not Linking",
    "investigation_steps": [
      "Verify that the account number and IFSC code are correctly registered in the NPCI mapper.",
      "Check if the bank account is active, operative, and not frozen or dormant.",
      "Confirm that the mobile number linked to UPI matches the mobile number registered in CBS for that account.",
      "Review NPCI account linking API response logs for error codes.",
      "Check if the account type is eligible for UPI (e.g., current, savings) per NPCI guidelines."
    ],
    "next_best_actions": [
      "If the account is dormant, initiate account reactivation per bank policy and then retry linking.",
      "If mobile number mismatch is found, update the mobile number in CBS after due verification.",
      "Raise a service request with NPCI if the account linking failure is due to mapper unavailability.",
      "Coordinate with the UPI technical team to retry the linking API call.",
      "Document the failure reason in the complaint management system and track till resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Mobile Number Not Registered",
    "investigation_steps": [
      "Check the CBS records to verify if any mobile number is registered for the customer's account.",
      "Cross-verify with the account opening form and KYC documents for the mobile number provided.",
      "Confirm whether the mobile number was previously registered and subsequently removed.",
      "Check the NPCI mapper to see if the mobile number is mapped to a different account."
    ],
    "next_best_actions": [
      "Initiate a request to register the correct mobile number in CBS after identity verification.",
      "Once CBS is updated, update the NPCI mapper via the bank's scheduled sync process.",
      "Advise the branch operations team to complete the mobile number update within SLA.",
      "Track the update and confirm successful registration in the NPCI mapper before closing the complaint."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Mobile Number Verification Failed",
    "investigation_steps": [
      "Check if the OTP delivery was successful by reviewing SMS gateway logs.",
      "Verify if the mobile number entered by the user matches the number registered in CBS.",
      "Check for OTP expiry or session timeout issues in the UPI app authentication logs.",
      "Confirm if the customer's SIM is active and network connectivity was available at the time."
    ],
    "next_best_actions": [
      "If OTP delivery failed, escalate to the SMS gateway vendor for investigation.",
      "If number mismatch is found, update the mobile number in CBS after proper verification.",
      "If session timeout is the root cause, coordinate with the UPI platform team to optimize OTP validity periods.",
      "Log the issue in the telecom-related failure tracker for pattern analysis."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "SIM Verification Failed",
    "investigation_steps": [
      "Check UPI app logs for the SIM binding error code returned during verification.",
      "Verify if the SIM card in the device matches the registered mobile number in CBS.",
      "Confirm if the telecom operator returned a successful SIM verification response.",
      "Check if the customer recently changed their SIM or ported to a new operator.",
      "Review NPCI's device binding and SIM verification API response logs."
    ],
    "next_best_actions": [
      "If the SIM was recently changed, initiate re-verification after confirming the new SIM is active and stable.",
      "Coordinate with the UPI platform team to retry SIM verification.",
      "If telecom operator APIs are failing, escalate to the telecom integration team.",
      "Advise the UPI operations team to monitor SIM verification failure rates for systemic issues."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Device Binding Failed",
    "investigation_steps": [
      "Review UPI app device binding logs for the specific failure code.",
      "Check if the device has been previously bound and whether a re-binding limit has been reached.",
      "Verify if the device IMEI or hardware fingerprint matches NPCI's allowed binding parameters.",
      "Confirm if multiple device binding attempts were made and if a cooling-off period is active.",
      "Check for any OS or app version incompatibilities."
    ],
    "next_best_actions": [
      "If binding limit is exceeded, initiate a manual device binding reset after identity verification.",
      "Escalate to the UPI platform/technical team if device binding API is returning system errors.",
      "Coordinate with NPCI if device binding failures are due to mapper-level restrictions.",
      "Log the failure and monitor for patterns if multiple customers report the same issue."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI ID Creation Failed",
    "investigation_steps": [
      "Check NPCI VPA creation API logs for the error response code.",
      "Verify if the desired UPI ID (VPA) already exists in the NPCI mapper.",
      "Confirm the customer's mobile number and bank account are correctly linked in NPCI.",
      "Check for special characters or invalid formats in the requested UPI ID."
    ],
    "next_best_actions": [
      "If VPA already exists, suggest alternate VPA patterns to the operations team.",
      "If account/mobile mapping is missing, resolve the mapping issue first, then retry VPA creation.",
      "If the error is system-level, escalate to the UPI tech team for API fix.",
      "Document and track the VPA creation failure in the complaint system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI ID Already Exists",
    "investigation_steps": [
      "Search NPCI mapper to confirm if the requested VPA is already registered.",
      "Identify which account/customer the existing VPA is mapped to.",
      "Check if the VPA was previously created by the same customer and not deactivated.",
      "Confirm whether the VPA conflict is due to a system error or a genuine duplicate."
    ],
    "next_best_actions": [
      "If the VPA belongs to the same customer on a different device, guide the ops team to deactivate the old mapping before creating a new one.",
      "If VPA belongs to a different customer, advise the customer-facing team to suggest an alternate VPA.",
      "Escalate to NPCI if there is a mapper inconsistency causing false duplicate flags.",
      "Document the case and resolution steps in the knowledge base."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Unable to Set UPI PIN",
    "investigation_steps": [
      "Check if the customer's debit card details used for PIN setup are valid and linked to the account.",
      "Verify if the card is active, unexpired, and not blocked.",
      "Review UPI PIN setup API logs for the error code returned.",
      "Check if the bank's HSM (Hardware Security Module) or PIN block generation service is operational.",
      "Confirm if there are any CBS-level restrictions on the account."
    ],
    "next_best_actions": [
      "If the card is inactive or expired, initiate card replacement/reactivation through the card management team.",
      "If HSM or PIN services are down, escalate to the infra/security team for immediate resolution.",
      "Coordinate with the UPI tech team to retry PIN setup after resolving the root cause.",
      "Monitor and report if PIN setup failures are widespread to detect systemic issues."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI PIN Generation Failed",
    "investigation_steps": [
      "Retrieve the PIN generation request logs from the UPI switch and identify the failure point.",
      "Verify the customer's debit card number and expiry entered during PIN generation.",
      "Check connectivity between the UPI platform and the bank's card management / HSM service.",
      "Confirm if the NPCI PIN generation API returned an error or timed out."
    ],
    "next_best_actions": [
      "If it is a connectivity issue, escalate to the infra team to restore API communication.",
      "If incorrect card details are suspected, verify with the card management system and retry.",
      "If NPCI API is unresponsive, raise a P1 incident with the NPCI technical helpdesk.",
      "Track resolution within SLA and update the complaint management system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI PIN Reset Failed",
    "investigation_steps": [
      "Check the UPI PIN reset API logs for failure codes.",
      "Verify that the debit card details used for reset authentication are valid.",
      "Confirm if the account has exceeded the maximum PIN reset attempts allowed.",
      "Check if the HSM service is operational and responding to PIN block requests."
    ],
    "next_best_actions": [
      "If the reset attempt limit is exceeded, enforce a cooling-off period as per policy and log the case.",
      "If HSM is non-functional, escalate as a critical infra incident.",
      "After root cause resolution, retry the PIN reset from the bank's admin UPI console.",
      "Update the fraud monitoring team if PIN reset failures suggest a brute-force attempt."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Incorrect UPI PIN",
    "investigation_steps": [
      "Check the UPI transaction logs to confirm the number of incorrect PIN attempts made.",
      "Verify if the account is in a locked or restricted state due to consecutive wrong PIN entries.",
      "Review if the customer has recently reset their PIN and may be using an old PIN."
    ],
    "next_best_actions": [
      "If the account is locked due to wrong PIN, initiate PIN unlock after identity verification.",
      "If the error is repeated and suspicious, flag the account for fraud review.",
      "Coordinate with the customer touchpoint team to advise the customer to reset their PIN via the appropriate channel.",
      "Document the incident and ensure the fraud alert team is notified if unauthorized PIN attempts are suspected."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Forgot UPI PIN",
    "investigation_steps": [
      "Verify the customer's identity using available KYC data in CBS.",
      "Check if the customer has a valid linked debit card to initiate the PIN reset flow.",
      "Confirm the account status is active and eligible for UPI PIN reset."
    ],
    "next_best_actions": [
      "Initiate a UPI PIN reset workflow using the customer's debit card credentials.",
      "If the debit card is unavailable or expired, first coordinate card re-issuance, then initiate PIN reset.",
      "Ensure the reset flow is completed and a new PIN is successfully set before closing the complaint.",
      "Communicate completion status to the relevant customer servicing team."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI PIN Locked",
    "investigation_steps": [
      "Confirm the PIN lock status from UPI switch logs.",
      "Check the number of consecutive wrong PIN attempts that triggered the lock.",
      "Verify if the lock was triggered by the customer's own failed attempts or if unauthorized access is suspected.",
      "Cross-reference with fraud monitoring dashboards for suspicious activity."
    ],
    "next_best_actions": [
      "Initiate PIN unlock after identity verification if no fraud is suspected.",
      "If fraud is suspected, place a temporary hold on UPI transactions and route to the fraud investigation team.",
      "After unlock, instruct the customer service team to guide the customer through PIN reset.",
      "Document the locking reason and resolution in the complaint system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Too Many Incorrect PIN Attempts",
    "investigation_steps": [
      "Review UPI switch logs to confirm the number of failed PIN attempts and timestamps.",
      "Determine if the attempts were made from a single device or multiple devices.",
      "Check fraud monitoring systems for any associated alerts on the account.",
      "Verify if the customer was present and knowingly entering the PIN."
    ],
    "next_best_actions": [
      "Temporarily restrict UPI transactions on the account per the bank's security policy.",
      "Escalate to the fraud team if multiple devices or unusual geolocation is detected.",
      "After investigation, unlock the account and require PIN reset via secure authentication.",
      "Log a security incident report if unauthorized access is confirmed."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI App Login Failed",
    "investigation_steps": [
      "Review UPI app authentication logs for the login error code.",
      "Check if the customer's registered mobile number and device binding are intact in the system.",
      "Verify if the bank's UPI app authentication service (OAuth/token service) is operational.",
      "Check for any recent app updates that may have broken the login flow."
    ],
    "next_best_actions": [
      "If the auth service is down, escalate to the platform/infra team as a P1 incident.",
      "If device binding has changed, initiate re-binding through the secure re-registration process.",
      "If an app bug is identified, coordinate with the mobile app development team for a hotfix.",
      "Monitor login failure rates on the ops dashboard for systemic issues."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI App Crashing",
    "investigation_steps": [
      "Collect crash logs from the mobile app crash analytics platform (e.g., Firebase Crashlytics).",
      "Identify the specific screen or action that triggers the crash.",
      "Check the app version, OS version, and device model for compatibility issues.",
      "Verify if the crash is widespread or isolated to specific device models/OS versions.",
      "Check if any recent app update deployment coincides with the crash spike."
    ],
    "next_best_actions": [
      "Escalate crash logs to the mobile development team with full reproduction steps.",
      "If crash is version-specific, initiate an emergency rollback or hotfix release.",
      "Coordinate with QA team to reproduce and validate the fix before re-deployment.",
      "Monitor crash rates post-fix deployment to confirm resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI App Not Responding",
    "investigation_steps": [
      "Check UPI backend API response times for latency or timeout issues.",
      "Review app performance monitoring tools for memory/CPU spikes.",
      "Verify if the issue is occurring for all customers or a specific segment.",
      "Check if any backend services (authentication, transaction processing) are slow or unresponsive."
    ],
    "next_best_actions": [
      "If backend APIs are slow, escalate to the infra/DevOps team to scale resources.",
      "If the app has a memory leak or front-end issue, escalate to the mobile development team.",
      "Implement app performance monitoring alerts to detect recurrence early.",
      "Communicate status updates to customer-facing teams if the outage is widespread."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Unable to Access UPI Services",
    "investigation_steps": [
      "Check the UPI switch and NPCI connectivity status for downtime or degradation.",
      "Verify if the bank's UPI platform is operational by checking internal health dashboards.",
      "Identify if the issue is limited to one channel (app/web) or all channels.",
      "Check NPCI's status portal for scheduled maintenance or outage notifications."
    ],
    "next_best_actions": [
      "If NPCI is down, monitor their status updates and communicate expected resolution time to ops teams.",
      "If the bank's own UPI platform is down, escalate to the infra team for immediate remediation.",
      "Publish an internal advisory for customer-facing teams about the service outage.",
      "Restore services and validate end-to-end UPI transaction flow before declaring resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Bank Server Unavailable",
    "investigation_steps": [
      "Check the bank's core banking system (CBS) and UPI switch uptime and connectivity.",
      "Review server health monitoring dashboards for any alerts or errors.",
      "Identify if the server unavailability is scheduled maintenance or an unplanned outage.",
      "Check network and firewall logs for any connectivity disruptions between UPI and CBS."
    ],
    "next_best_actions": [
      "Escalate to the infra/operations team to restore server availability immediately.",
      "If scheduled maintenance, ensure affected UPI transactions are queued for retry post-restoration.",
      "Notify the business continuity team to activate DR (Disaster Recovery) procedures if needed.",
      "Post-recovery, run end-to-end transaction validation tests before resuming normal operations."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Payment Failed",
    "investigation_steps": [
      "Retrieve the transaction ID and check NPCI switch logs for the failure reason code.",
      "Verify if the customer's account had sufficient balance at the time of payment.",
      "Check if the beneficiary VPA or bank account details are valid.",
      "Review if any fraud rules or velocity checks blocked the transaction.",
      "Confirm if the failure was at the payer bank, NPCI, or beneficiary bank level."
    ],
    "next_best_actions": [
      "If the failure was due to beneficiary bank rejection, document the reason and advise the business team.",
      "If a fraud rule triggered, route to the fraud operations team for review.",
      "If it is a technical failure, retry the transaction manually if idempotency is confirmed.",
      "Ensure no debit was made; if debit occurred without credit, initiate reversal."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Payment Pending",
    "investigation_steps": [
      "Check NPCI UPI switch for the transaction state (initiated, pending, deemed).",
      "Verify if the pending state is within the allowed resolution window (T+1 for UPI).",
      "Confirm if the beneficiary bank has received the credit instruction.",
      "Review CBS and UPI switch for any reconciliation mismatches."
    ],
    "next_best_actions": [
      "If within T+1, monitor for auto-resolution by NPCI.",
      "If beyond T+1, initiate a dispute via NPCI dispute management system.",
      "Coordinate with the beneficiary bank's dispute desk if credit has not been applied.",
      "Ensure the customer's account is not double-debited and reconcile accordingly."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Payment Timed Out",
    "investigation_steps": [
      "Check UPI switch logs for the timeout response code and the point of timeout.",
      "Determine if the timeout was at the payer bank, NPCI switch, or beneficiary bank.",
      "Verify if the debit was executed before the timeout and if a reversal was triggered.",
      "Check NPCI's status for any network-level latency events at the time of the transaction."
    ],
    "next_best_actions": [
      "If debit occurred but no credit was given, initiate auto-reversal or manual reversal.",
      "Raise an exception log in the reconciliation system for the timed-out transaction.",
      "Escalate to NPCI if timeout rates are abnormally high.",
      "Review and optimize timeout configurations in the UPI switch to prevent recurrence."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Transaction Timed Out",
    "investigation_steps": [
      "Retrieve transaction logs and identify at which stage the timeout occurred.",
      "Check if the transaction ID exists in NPCI's records and its current state.",
      "Confirm whether the debit was posted to the customer's account in CBS.",
      "Review API gateway and UPI switch timeout settings."
    ],
    "next_best_actions": [
      "If debit occurred without a corresponding credit or reversal, initiate reconciliation and reverse the debit.",
      "Log the timed-out transaction for the daily reconciliation sweep.",
      "Escalate to the tech team if timeout settings are misconfigured.",
      "Monitor timeout rates and raise with NPCI if systemic."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Amount Debited but Beneficiary Not Credited",
    "investigation_steps": [
      "Confirm the debit in CBS and the corresponding NPCI transaction reference.",
      "Check NPCI switch logs to determine if the credit instruction was sent to the beneficiary bank.",
      "Contact the beneficiary bank's operations team to confirm receipt and processing of the credit.",
      "Check if the credit was rejected by the beneficiary bank due to account issues."
    ],
    "next_best_actions": [
      "If credit instruction was sent but not processed, escalate to the beneficiary bank.",
      "If credit instruction was not sent by NPCI, raise a dispute with NPCI.",
      "If credit is confirmed stuck, initiate a manual credit to the beneficiary or a reversal to the payer.",
      "Ensure transaction is updated in the reconciliation system with the resolution outcome."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Amount Debited but Transaction Failed",
    "investigation_steps": [
      "Retrieve NPCI transaction logs to confirm the final status (failed/reversed).",
      "Verify if the debit was posted in CBS before the failure response was received.",
      "Check if auto-reversal was initiated and the expected reversal credit timeline.",
      "Confirm the failure reason code from the NPCI switch."
    ],
    "next_best_actions": [
      "If reversal is pending, monitor and escalate to ensure it completes within NPCI's T+1 policy.",
      "If reversal has not been triggered, initiate a manual reversal through CBS.",
      "Log the case in the reconciliation register and reconcile against NPCI settlement files.",
      "Report recurring debits-on-failure patterns to the UPI tech team for fix."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Beneficiary Credited but Amount Debited Twice",
    "investigation_steps": [
      "Identify both transaction IDs and compare them in NPCI logs.",
      "Verify if the two debits correspond to two separate NPCI transaction references or are duplicate entries.",
      "Check if the idempotency key was honored by the UPI switch.",
      "Review CBS postings to confirm the number of debits on the account."
    ],
    "next_best_actions": [
      "Initiate a reversal for the duplicate/extra debit from CBS.",
      "Coordinate with NPCI to confirm whether both transactions were settled.",
      "Raise a chargeback or debit reversal request for the erroneous second debit.",
      "Escalate to the UPI tech team to fix idempotency handling to prevent recurrence."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Duplicate Debit",
    "investigation_steps": [
      "Review CBS debit entries and match each against NPCI transaction IDs.",
      "Determine if two separate NPCI requests were generated or one request was double-posted.",
      "Check the UPI switch for duplicate transaction handling logic.",
      "Review the payment initiation logs to identify if the request was sent twice."
    ],
    "next_best_actions": [
      "Reverse the duplicate debit from CBS after confirming it is not a legitimate transaction.",
      "Escalate to the UPI tech team if duplicate requests are being generated due to a software bug.",
      "Update reconciliation records to reflect the corrected balance.",
      "Notify the fraud team if duplicate debits appear to be externally triggered."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Duplicate Transaction",
    "investigation_steps": [
      "Pull all transaction logs matching the transaction amount, time, and beneficiary.",
      "Compare NPCI transaction references to determine if one or two payment orders were placed.",
      "Check the UPI switch idempotency and de-duplication logic.",
      "Verify CBS entries to confirm whether one or both transactions were posted."
    ],
    "next_best_actions": [
      "If both transactions settled, initiate reversal of the duplicate via NPCI dispute or direct CBS credit.",
      "File a defect report with the UPI platform team for the duplicate generation issue.",
      "Reconcile the account and notify the reconciliation team.",
      "Escalate to NPCI if the duplicate is on their end."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Double Charge on Same Transaction",
    "investigation_steps": [
      "Retrieve both charge records from CBS and match them to NPCI transaction references.",
      "Check if the merchant or payment gateway submitted the same payment request twice.",
      "Verify UPI switch logs to confirm whether one or two authorization requests were processed.",
      "Contact the acquiring bank/merchant bank to confirm the settlement amount received."
    ],
    "next_best_actions": [
      "Reverse the extra charge from the customer's account after confirming it is erroneous.",
      "Coordinate with the merchant's acquiring bank to reconcile the settlement.",
      "Raise a chargeback if the merchant refuses to acknowledge the double charge.",
      "Report the pattern to the fraud team if the same merchant has multiple such instances."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Refund Not Received",
    "investigation_steps": [
      "Confirm with the merchant or originating entity that the refund was initiated.",
      "Check NPCI refund transaction logs for the refund reference number and status.",
      "Verify if the refund credit was received by the bank and posted to the correct account.",
      "Check if the refund was initiated to the correct VPA or account number."
    ],
    "next_best_actions": [
      "If the refund was sent by the merchant but not credited, check CBS and initiate internal credit.",
      "If refund has not been initiated by the merchant, coordinate with the merchant's acquirer bank.",
      "If refund is stuck at NPCI, raise a dispute with NPCI's dispute management desk.",
      "Update the complaint system with the refund reference number and expected credit date."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Refund Delayed",
    "investigation_steps": [
      "Check the refund initiation date and compare it against NPCI's standard refund timelines.",
      "Retrieve the refund transaction ID and track its status in NPCI switch logs.",
      "Verify if the delay is at the merchant end, NPCI, or the beneficiary bank.",
      "Confirm if there is a batch processing delay in the settlement cycle."
    ],
    "next_best_actions": [
      "If beyond the SLA, escalate to NPCI's operations team with the refund reference.",
      "Coordinate with the merchant acquirer to confirm the refund was dispatched.",
      "Expedite the credit to the customer's account if the funds are confirmed received at the bank.",
      "Set a follow-up task in the CRM to track until credit confirmation."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Refund Failed",
    "investigation_steps": [
      "Retrieve the refund transaction log and identify the failure reason code.",
      "Check if the original payment VPA or account is still active and valid.",
      "Verify if the refund was rejected by the payer's bank.",
      "Check if the refund amount exceeds the original transaction amount (not allowed under NPCI rules)."
    ],
    "next_best_actions": [
      "If the VPA is inactive, coordinate with the merchant and NPCI to redirect the refund.",
      "If the refund was rejected by the bank, investigate the rejection reason and reprocess.",
      "Coordinate with the merchant to re-initiate the refund after fixing the root cause.",
      "Update the reconciliation team to track the refund status."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Merchant Refund Pending",
    "investigation_steps": [
      "Verify with the merchant's acquiring bank whether the refund has been initiated.",
      "Check the merchant's settlement account to confirm receipt of payment.",
      "Review NPCI merchant transaction logs for any refund trigger by the merchant.",
      "Confirm the merchant's SLA for processing refunds."
    ],
    "next_best_actions": [
      "Follow up with the merchant's acquiring bank to expedite the refund initiation.",
      "If the merchant is non-cooperative, escalate to the bank's merchant services team.",
      "Initiate a chargeback process if the merchant's refund exceeds the permissible timeline.",
      "Track the refund pending case in the dispute management system with deadlines."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Chargeback Not Processed",
    "investigation_steps": [
      "Verify that the chargeback request was correctly submitted within the allowable dispute window.",
      "Check the chargeback management system for the status of the request.",
      "Confirm that all required documentation (transaction proof, merchant response) was submitted.",
      "Review NPCI's chargeback processing logs to check if the request was received."
    ],
    "next_best_actions": [
      "If the chargeback was not submitted correctly, reprocess it with correct documentation.",
      "Escalate to the dispute management team to manually push the chargeback to NPCI.",
      "Coordinate with the merchant's acquirer for chargeback acknowledgment.",
      "Set a tracking deadline in the dispute management system for resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Wrong Account Credited",
    "investigation_steps": [
      "Retrieve the beneficiary account details entered at the time of the transaction.",
      "Confirm from NPCI logs whether the payment was sent to the intended or wrong account.",
      "Identify the receiving bank and account holder details for the wrong credit.",
      "Verify if the transaction was initiated with the correct VPA or account number."
    ],
    "next_best_actions": [
      "Coordinate with the receiving bank to place a lien/hold on the wrongly credited amount.",
      "Initiate a recall or return transaction process with the beneficiary bank.",
      "Raise a NPCI dispute if the funds need to be recovered through the network.",
      "Document all inter-bank communication in the complaint management system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Wrong UPI ID Credited",
    "investigation_steps": [
      "Retrieve the VPA used for the transaction and confirm it in NPCI logs.",
      "Identify which account is mapped to the incorrect VPA.",
      "Confirm the intended beneficiary's VPA and the difference from the entered VPA.",
      "Check for typographical similarity between the two VPAs to rule out spoofing."
    ],
    "next_best_actions": [
      "Contact the bank where the wrong VPA is registered to recall the funds.",
      "Raise a recall request through NPCI's inter-bank recall mechanism.",
      "Escalate to the fraud team if the wrong VPA appears to be a spoofed or fraudulent ID.",
      "Update the reconciliation team and log the case for regulatory reporting if needed."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Transfer to Closed Account",
    "investigation_steps": [
      "Verify the account status of the beneficiary at the receiving bank.",
      "Check if NPCI's account validation returned the account as valid at the time of the transaction.",
      "Confirm if the receiving bank has bounced or returned the funds.",
      "Review whether the account was closed before or after the transaction was initiated."
    ],
    "next_best_actions": [
      "Coordinate with the beneficiary bank to confirm if funds were returned.",
      "If funds were not returned, initiate a formal recall request with the beneficiary bank.",
      "If the account was valid at transaction time but subsequently closed, escalate to NPCI.",
      "Credit returned funds back to the originator's account and close the complaint."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Beneficiary Not Credited",
    "investigation_steps": [
      "Confirm from NPCI switch logs whether the credit instruction was sent to the beneficiary bank.",
      "Verify the beneficiary bank's receipt and processing status.",
      "Check if the beneficiary account number and IFSC are correct in the transaction record.",
      "Confirm if the beneficiary bank rejected the credit and sent back a return."
    ],
    "next_best_actions": [
      "If the credit instruction was not sent by NPCI, raise a dispute with NPCI.",
      "If the credit was rejected by the beneficiary bank, identify the reason and coordinate reprocessing.",
      "If funds are confirmed not credited, either re-initiate the credit or reverse the debit to the payer.",
      "Update the complaint system and the reconciliation team with the resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Beneficiary Credit Delayed",
    "investigation_steps": [
      "Check NPCI settlement logs for the credit instruction timestamp.",
      "Verify the beneficiary bank's processing timelines and settlement batch schedules.",
      "Confirm if there is a known delay or outage at the beneficiary bank.",
      "Review NPCI's real-time gross settlement (RTGS) status for any delays."
    ],
    "next_best_actions": [
      "Coordinate with the beneficiary bank to expedite the credit posting.",
      "Raise a priority escalation with NPCI if delay exceeds the T+1 norm.",
      "Track the case with the beneficiary bank until credit is confirmed.",
      "Update the reconciliation team and notify the business team of the delay."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Payment Reversed Unexpectedly",
    "investigation_steps": [
      "Retrieve the reversal transaction ID from NPCI logs and identify who initiated the reversal.",
      "Check if the reversal was triggered by the beneficiary bank, NPCI, or the bank's own system.",
      "Review the reason code associated with the reversal.",
      "Confirm if the original payment was successful and if funds were credited to the beneficiary."
    ],
    "next_best_actions": [
      "If the reversal was triggered in error, raise a dispute with NPCI to re-initiate the original credit.",
      "Coordinate with the beneficiary bank to confirm their side of the reversal.",
      "If the reversal was legitimate (e.g., account closure), inform the relevant business team.",
      "Log the reversal reason in the complaint and reconciliation systems."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Payment Reversed After Success",
    "investigation_steps": [
      "Confirm the original payment success from NPCI switch logs.",
      "Identify the entity that initiated the post-success reversal and the timestamp.",
      "Check if the reversal was due to a system error, fraud flag, or manual intervention.",
      "Review fraud monitoring rules to determine if a false positive triggered the reversal."
    ],
    "next_best_actions": [
      "If the reversal was erroneous, coordinate to reinstate the original payment or re-initiate credit.",
      "If fraud was suspected, validate with the fraud team before reinstating the transaction.",
      "Ensure the beneficiary is not left without the credited amount.",
      "Document the incident and review fraud rules if false positives are causing reversals."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Auto-Debit Failed",
    "investigation_steps": [
      "Retrieve the auto-debit mandate details and check the NPCI mandate execution log.",
      "Confirm the customer's account had sufficient balance at the time of the auto-debit.",
      "Check if the mandate is active, valid, and within the authorized debit window.",
      "Review NPCI's response code for the failed debit instruction."
    ],
    "next_best_actions": [
      "If balance was insufficient, log the failure and notify the merchant/biller of the failed debit.",
      "If the mandate is inactive, investigate why it was deactivated and re-register if required.",
      "If the failure is a technical error, retry the auto-debit within the next permissible window.",
      "Update the mandate status in the UPI mandate management system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "AutoPay Registration Failed",
    "investigation_steps": [
      "Check the NPCI mandate creation API response for the specific failure code.",
      "Verify if the customer's VPA and bank account are active and eligible for mandate creation.",
      "Confirm the merchant's VPA is correctly registered and active.",
      "Check if the mandate amount and validity period comply with NPCI's AutoPay rules."
    ],
    "next_best_actions": [
      "If VPA is invalid, correct the VPA and retry mandate registration.",
      "If the mandate parameters are non-compliant, coordinate with the merchant to correct and resubmit.",
      "If the failure is system-level, escalate to the UPI tech team for resolution.",
      "Confirm mandate registration success in the NPCI system after fix."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "AutoPay Cancellation Failed",
    "investigation_steps": [
      "Retrieve the mandate cancellation request log from the UPI switch.",
      "Check NPCI's mandate management system for the current status of the mandate.",
      "Verify if the cancellation request was submitted before the next debit cycle.",
      "Identify any error code returned by the NPCI mandate revocation API."
    ],
    "next_best_actions": [
      "Retry the mandate cancellation from the bank's UPI admin console.",
      "Escalate to NPCI if the mandate is not cancelling due to a system error.",
      "Place a block on future auto-debits from the account as a protective measure while resolving.",
      "Confirm cancellation success in NPCI records and update the mandate management system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Standing Instruction Failed",
    "investigation_steps": [
      "Check the standing instruction execution log in CBS for the failure date and reason.",
      "Verify if the instruction parameters (amount, date, beneficiary) are still valid.",
      "Confirm the customer's account balance was sufficient on the execution date.",
      "Check if any account restriction or freeze prevented the debit."
    ],
    "next_best_actions": [
      "If balance was insufficient, log and notify the relevant team per bank policy.",
      "If account is restricted, investigate and lift the restriction if valid.",
      "Reprocess the standing instruction if it was a one-time technical failure.",
      "Review and update standing instruction parameters if they have become invalid."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Subscription Payment Failed",
    "investigation_steps": [
      "Retrieve the subscription mandate ID and check NPCI execution logs.",
      "Verify account balance and mandate authorization at the time of payment.",
      "Check if the subscription merchant's VPA is still active.",
      "Review any NPCI rule changes that may have affected mandate execution."
    ],
    "next_best_actions": [
      "If balance was insufficient, log the failure and notify the merchant per the UPI AutoPay framework.",
      "If the merchant VPA is inactive, coordinate with the merchant to update VPA and re-register the mandate.",
      "If a technical failure, retry the payment in the next allowable window.",
      "Update the mandate execution log in the UPI mandate management system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Recurring Payment Failed",
    "investigation_steps": [
      "Check NPCI recurring mandate execution log for the failure reason code.",
      "Verify mandate validity, authorization, and the customer's account balance.",
      "Confirm if the merchant initiated the debit request correctly.",
      "Check for any technical failures on the NPCI end at the time of execution."
    ],
    "next_best_actions": [
      "Log the failure and report to the merchant's acquiring bank.",
      "Retry the recurring payment in the next valid window if authorized.",
      "If the mandate has expired, coordinate with the merchant to request a new mandate from the customer.",
      "Track and reconcile failed recurring payments in the mandate management system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Mandate Registration Failed",
    "investigation_steps": [
      "Review the NPCI mandate registration API response for the error code.",
      "Verify the customer's VPA, bank account, and the merchant's registration details.",
      "Confirm the mandate amount is within the permissible limit defined by NPCI.",
      "Check if the customer provided UPI PIN approval for the mandate."
    ],
    "next_best_actions": [
      "If missing PIN approval, re-initiate the mandate request for customer approval.",
      "If parameters are non-compliant, correct them and resubmit.",
      "If the error is system-level, escalate to the UPI technical team.",
      "Confirm mandate registration in NPCI records post-resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Mandate Modification Failed",
    "investigation_steps": [
      "Check NPCI mandate modification API logs for the error code.",
      "Verify if the modification request is within permissible limits (e.g., amount cap, frequency).",
      "Confirm if the existing mandate is in an active state eligible for modification.",
      "Check if the customer approved the modification request via UPI PIN."
    ],
    "next_best_actions": [
      "If customer approval is pending, re-trigger the modification approval request.",
      "If the modification parameters are invalid, coordinate with the merchant to correct and resubmit.",
      "Escalate to the UPI tech team if a system error is preventing modification.",
      "Update the mandate management system once modification is successful."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Mandate Cancellation Failed",
    "investigation_steps": [
      "Retrieve mandate cancellation API logs and identify the failure reason.",
      "Check the current mandate status in NPCI's mandate registry.",
      "Confirm if any pending debit execution is blocking the cancellation.",
      "Verify if the cancellation request was made by an authorized party."
    ],
    "next_best_actions": [
      "If a pending debit is blocking, resolve or reject the pending debit first, then retry cancellation.",
      "Escalate to NPCI mandate team if the cancellation is stuck at the switch level.",
      "Place a soft block on future debits as an interim measure.",
      "Confirm cancellation in NPCI records and update internal systems."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Mandate Executed Incorrectly",
    "investigation_steps": [
      "Compare the mandate terms (amount, frequency, start/end date) with the actual execution record.",
      "Check NPCI mandate execution log for the executed amount and timestamp.",
      "Confirm if the merchant's debit request matched the pre-approved mandate terms.",
      "Identify if incorrect execution was due to a system error or merchant submission error."
    ],
    "next_best_actions": [
      "If the debit amount exceeds the mandate, initiate reversal of the excess amount.",
      "Report the incorrect execution to the merchant's acquiring bank.",
      "Escalate to NPCI if mandate enforcement controls failed to validate execution parameters.",
      "Update the mandate management system and flag for audit review."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Collect Request Failed",
    "investigation_steps": [
      "Retrieve the collect request ID and check NPCI collect request logs.",
      "Verify if the payer's VPA is valid and active.",
      "Check if the collect request expired before the payer responded.",
      "Review the error code returned by the NPCI switch."
    ],
    "next_best_actions": [
      "If the VPA is invalid, notify the requester to correct the payer's VPA and retry.",
      "If expired, re-initiate the collect request with an appropriate validity window.",
      "If system error, escalate to the UPI technical team.",
      "Log the failure and track in the complaint management system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Collect Request Not Received",
    "investigation_steps": [
      "Confirm from NPCI logs that the collect request was sent to the payer's UPI app.",
      "Check if the payer's UPI app notification service is active.",
      "Verify if the payer's device is registered and the app is properly installed.",
      "Check for notification delivery failure in push notification gateway logs."
    ],
    "next_best_actions": [
      "If the collect request was sent but the notification was not delivered, escalate to the push notification team.",
      "Verify payer's app and device registration and advise them to refresh their app.",
      "Re-send the collect request after confirming payer's device is active.",
      "Document the failure in the complaint system and track resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Collect Request Expired",
    "investigation_steps": [
      "Confirm the collect request creation timestamp and expiry window from NPCI logs.",
      "Verify if the payer was notified in time and what response was received.",
      "Check if the expiry period set by the requester was appropriate.",
      "Confirm the payer did not approve the request within the window."
    ],
    "next_best_actions": [
      "Re-initiate a new collect request with an adequate expiry window.",
      "Advise the requesting team to set appropriate expiry periods in future requests.",
      "If the payer repeatedly fails to respond, investigate if there is a notification issue.",
      "Log and close the expired collect request in the complaint system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Fake Collect Request",
    "investigation_steps": [
      "Retrieve details of the collect request (requester's VPA, amount, description) from NPCI logs.",
      "Verify if the requester VPA belongs to a registered and verified entity.",
      "Check for similar collect requests sent to multiple customers from the same VPA.",
      "Cross-reference with the fraud monitoring system for known fraudulent VPAs."
    ],
    "next_best_actions": [
      "Block the fraudulent VPA in the bank's UPI switch immediately.",
      "Report the fraudulent VPA to NPCI for blacklisting.",
      "Notify the fraud investigation team and initiate a formal fraud report.",
      "Alert other banks via NPCI's fraud reporting mechanism if mass fraud is suspected."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Fraudulent Collect Request",
    "investigation_steps": [
      "Analyze the collect request details (amount, VPA, description) for fraud indicators.",
      "Check if the payer approved and paid the fraudulent collect request.",
      "Identify the fraudster's VPA and linked bank account from NPCI records.",
      "Review fraud monitoring alerts for patterns of similar fraudulent collect requests."
    ],
    "next_best_actions": [
      "If payment was made, immediately freeze the receiving account and coordinate for fund recovery.",
      "Block the fraudulent VPA across the bank's UPI system.",
      "Report the fraud to NPCI and the receiving bank for coordinated action.",
      "File a complaint with the cybercrime authorities and document all evidence."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Unauthorized UPI Transaction",
    "investigation_steps": [
      "Retrieve transaction details and compare device ID, IP, and geolocation with customer's history.",
      "Check if the customer's UPI PIN was compromised.",
      "Review NPCI logs for the originating device and UPI app used.",
      "Check fraud monitoring system for alerts on the account."
    ],
    "next_best_actions": [
      "Immediately block the customer's UPI access pending investigation.",
      "Initiate a recall/chargeback for the unauthorized transaction amount.",
      "Escalate to the fraud investigation team for full forensic review.",
      "Report the incident to NPCI and file a regulatory report if required."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Suspicious UPI Transaction",
    "investigation_steps": [
      "Review the flagged transaction for indicators like unusual amount, new beneficiary, odd timing.",
      "Cross-reference with the fraud scoring model output for the transaction.",
      "Check customer transaction history for behavioral deviations.",
      "Verify if the customer's device or SIM has changed recently."
    ],
    "next_best_actions": [
      "Place a temporary hold on the transaction pending verification.",
      "Initiate outreach to the customer through the bank's secure channel for confirmation.",
      "If fraud is confirmed, escalate to the fraud team and initiate reversal proceedings.",
      "Update the fraud monitoring system with the case details."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Account Compromised",
    "investigation_steps": [
      "Check all recent transactions and login sessions on the compromised account.",
      "Verify if the registered mobile number or device binding was changed without authorization.",
      "Review NPCI logs for any VPA changes, new device registrations, or PIN changes.",
      "Cross-check with the fraud monitoring system for associated alerts."
    ],
    "next_best_actions": [
      "Immediately suspend UPI access on the compromised account.",
      "Initiate reversal for all unauthorized transactions.",
      "Reset the account's UPI registration and require fresh re-registration after identity verification.",
      "Report the compromise to NPCI and file an incident report with cybercrime authorities."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Fraud Complaint",
    "investigation_steps": [
      "Document all transaction details reported in the fraud complaint.",
      "Review NPCI transaction logs, device info, and beneficiary details.",
      "Check the fraud management system for existing alerts linked to this account or beneficiary.",
      "Identify whether the fraud was social engineering, phishing, or technical compromise."
    ],
    "next_best_actions": [
      "Freeze UPI transactions on the account as a precautionary measure.",
      "Initiate the formal fraud investigation process per the bank's SOPs.",
      "Coordinate with the beneficiary bank to freeze the receiving account and recover funds.",
      "File a complaint with the National Cyber Crime Reporting Portal (NCRP) and share evidence."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Phishing Through UPI",
    "investigation_steps": [
      "Collect all communication (SMS, emails, links) the customer received as part of the phishing attempt.",
      "Verify if the customer clicked any fake UPI link or shared their PIN/OTP.",
      "Check if any transactions were executed after the phishing contact.",
      "Identify the fraudulent UPI handle or link used in the phishing attempt."
    ],
    "next_best_actions": [
      "If transactions occurred, initiate recall/chargeback and freeze the fraudster's receiving account.",
      "Report the phishing URL/VPA to NPCI and cybersecurity authorities for takedown.",
      "Coordinate with the IT security team to block phishing domains from bank communication channels.",
      "Issue an internal advisory to the customer service team on the phishing pattern."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "QR Code Not Working",
    "investigation_steps": [
      "Verify whether the QR code is a static or dynamic QR and check its format compliance.",
      "Scan the QR code using internal tools to confirm the encoded VPA and amount.",
      "Check if the merchant's VPA embedded in the QR is active and valid.",
      "Review if the QR code was generated correctly by the merchant's POS or payment app."
    ],
    "next_best_actions": [
      "If the VPA is invalid or inactive, coordinate with the merchant to generate a new QR code.",
      "If the QR format is incorrect, advise the merchant acquirer to regenerate a compliant QR.",
      "Escalate to the UPI tech team if the QR scanning functionality is broken.",
      "Document the failure and merchant details for follow-up."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "QR Code Payment Failed",
    "investigation_steps": [
      "Retrieve the QR payment transaction reference and check NPCI switch logs.",
      "Confirm the VPA embedded in the QR is active and correctly resolving in NPCI.",
      "Check if the payment failure was due to a network error, VPA issue, or bank server error.",
      "Verify if the customer's account was debited despite the failure."
    ],
    "next_best_actions": [
      "If debited without credit, initiate reversal of the debit amount.",
      "If the VPA in the QR is incorrect, alert the merchant to update their QR code.",
      "Escalate to the UPI tech team if the QR payment gateway is experiencing errors.",
      "Log the case and reconcile the transaction outcome."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "QR Code Fraud",
    "investigation_steps": [
      "Retrieve and analyze the QR code reported as fraudulent.",
      "Identify the VPA embedded in the fraudulent QR code.",
      "Check NPCI mapper to trace the account linked to the fraudulent VPA.",
      "Review transaction history for payments made via the fraudulent QR to estimate the fraud volume."
    ],
    "next_best_actions": [
      "Block the fraudulent VPA immediately in the bank's UPI system.",
      "Report the fraudulent VPA to NPCI for network-wide blacklisting.",
      "Coordinate with the receiving bank to freeze the linked account and recover funds.",
      "Report the QR fraud to law enforcement and NPCI's fraud reporting team."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Merchant QR Invalid",
    "investigation_steps": [
      "Validate the merchant's QR code using a QR scanner tool.",
      "Check if the merchant's VPA is correctly registered in NPCI's mapper.",
      "Verify if the QR code was generated from the bank's or a third-party's merchant onboarding platform.",
      "Confirm whether the QR format (BharatQR, UPI QR) is compliant with NPCI standards."
    ],
    "next_best_actions": [
      "If the VPA is incorrect, coordinate with the merchant's acquiring team to regenerate the QR.",
      "If the QR format is non-compliant, advise the merchant to use the correct QR generation tool.",
      "Escalate to the merchant onboarding team to re-issue a valid QR.",
      "Verify and validate the new QR code before the merchant uses it."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Static QR Not Working",
    "investigation_steps": [
      "Scan the static QR using an internal tool to confirm the VPA and amount encoded.",
      "Check if the merchant's registered VPA in NPCI is active and resolving correctly.",
      "Determine if the static QR was physically damaged, faded, or tampered with.",
      "Verify the QR code was generated correctly during merchant onboarding."
    ],
    "next_best_actions": [
      "If VPA is inactive, reactivate it in NPCI and issue a new static QR to the merchant.",
      "If the QR is physically damaged, arrange for reprint and re-distribution.",
      "Coordinate with the merchant acquirer team to replace the static QR.",
      "Conduct a test scan post-replacement to confirm functionality."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Dynamic QR Not Generated",
    "investigation_steps": [
      "Check the merchant's POS system or payment gateway for errors in dynamic QR generation.",
      "Review the bank's or payment gateway's QR generation API logs for errors.",
      "Verify if the merchant's integration with the QR generation API is functioning correctly.",
      "Check for any expired API credentials or integration configuration issues."
    ],
    "next_best_actions": [
      "Escalate to the merchant technical integration team to diagnose the QR generation failure.",
      "If API credentials have expired, renew them and test QR generation.",
      "If the payment gateway is down, escalate to the gateway operations team.",
      "Test dynamic QR generation after resolution and confirm with the merchant."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Merchant Payment Not Received",
    "investigation_steps": [
      "Check NPCI transaction logs to confirm the payment was sent to the merchant's VPA.",
      "Verify if the credit was posted to the merchant's linked bank account.",
      "Confirm the merchant's settlement cycle and whether the payment falls within a pending settlement batch.",
      "Check for any technical credits pending in the payment gateway."
    ],
    "next_best_actions": [
      "If the payment was credited to the merchant's bank account, share the credit reference with the merchant team.",
      "If the payment is pending in a settlement batch, confirm the settlement date and monitor.",
      "If payment failed before reaching the merchant, initiate reconciliation and re-credit if needed.",
      "Coordinate between the merchant's acquirer and the merchant for confirmation."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Merchant Settlement Delayed",
    "investigation_steps": [
      "Check the settlement batch schedule and confirm if the delay is within normal processing timelines.",
      "Review NPCI settlement files to confirm receipt of funds for the merchant.",
      "Verify if there are any holds on the merchant's settlement account.",
      "Check if the delay is due to a holiday, weekend, or NPCI system event."
    ],
    "next_best_actions": [
      "If delayed beyond SLA, escalate to the settlements team for priority processing.",
      "Coordinate with the merchant services team to communicate the delay and expected resolution.",
      "If there is a hold on the settlement, investigate the reason and lift it if valid.",
      "Monitor the next settlement cycle and confirm merchant receipt."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Merchant Settlement Failed",
    "investigation_steps": [
      "Check the settlement processing log for the merchant's settlement batch.",
      "Identify the failure reason (invalid account, system error, insufficient settlement funds).",
      "Verify the merchant's bank account details on record are correct and active.",
      "Confirm if NPCI settlement file was correctly transmitted to the bank."
    ],
    "next_best_actions": [
      "If account details are wrong, correct them after merchant verification and reprocess settlement.",
      "If a system error occurred, escalate to the settlements infra team for immediate fix.",
      "Reprocess the failed settlement in the next available settlement window.",
      "Notify the merchant services team and confirm successful credit post-resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Merchant Payment Pending",
    "investigation_steps": [
      "Retrieve the payment transaction ID and check NPCI switch for the current payment status.",
      "Confirm if the payment is pending at NPCI, the payer's bank, or the merchant's bank.",
      "Review settlement timelines to determine when the payment is expected to be credited.",
      "Check for any reconciliation or settlement holds on the merchant's account."
    ],
    "next_best_actions": [
      "If payment is within normal settlement timelines, monitor and confirm in the next cycle.",
      "If beyond SLA, escalate to the settlements and reconciliation team.",
      "Coordinate with the merchant's acquirer to provide status updates.",
      "Once credited, confirm resolution and close the complaint."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Lite Registration Failed",
    "investigation_steps": [
      "Check UPI Lite registration API logs for the failure code.",
      "Verify if the customer's account and device meet NPCI's UPI Lite eligibility criteria.",
      "Confirm if the customer's bank supports UPI Lite and is correctly integrated with NPCI.",
      "Check if the wallet creation in the UPI Lite ecosystem failed at the device or server level."
    ],
    "next_best_actions": [
      "If bank eligibility is the issue, check the bank's UPI Lite rollout status.",
      "Escalate to the UPI Lite technical team if the registration API is returning errors.",
      "Coordinate with NPCI if the failure is at the UPI Lite ecosystem level.",
      "Retry registration after resolving the identified root cause."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Lite Balance Not Updated",
    "investigation_steps": [
      "Check UPI Lite wallet balance records and compare with the last top-up or transaction.",
      "Verify the on-device wallet balance log against the bank's UPI Lite shadow ledger.",
      "Confirm if a top-up transaction completed but the balance was not credited to the UPI Lite wallet.",
      "Review NPCI's UPI Lite transaction logs for balance update status."
    ],
    "next_best_actions": [
      "Trigger a balance refresh/sync from the bank's UPI Lite management system.",
      "If a discrepancy is found, credit the missing balance to the UPI Lite wallet.",
      "Escalate to the UPI Lite tech team if the balance update API is failing.",
      "Reconcile the UPI Lite shadow ledger with the actual on-device wallet balance."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Lite Top-up Failed",
    "investigation_steps": [
      "Check the UPI Lite top-up transaction log for the failure code.",
      "Verify if the customer's bank account had sufficient balance for the top-up.",
      "Confirm if the debit was executed on the bank account despite the top-up failing.",
      "Review NPCI's UPI Lite top-up API response logs."
    ],
    "next_best_actions": [
      "If debited but UPI Lite balance not updated, reverse the debit or credit the UPI Lite wallet.",
      "If the failure was pre-debit, advise the operations team to retry the top-up.",
      "Escalate to the UPI Lite tech team if API failures are systematic.",
      "Reconcile the bank account and UPI Lite balance records."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Lite Balance Deducted Incorrectly",
    "investigation_steps": [
      "Retrieve the UPI Lite transaction log for the contested deduction.",
      "Compare the deducted amount with the intended transaction amount.",
      "Check if the deduction corresponds to an actual payment or an erroneous system entry.",
      "Review the UPI Lite shadow ledger for any discrepancies."
    ],
    "next_best_actions": [
      "If the deduction is erroneous, initiate a credit to the UPI Lite wallet for the incorrect amount.",
      "Escalate to the UPI Lite tech team to identify and fix the balance deduction bug.",
      "Reconcile the UPI Lite shadow ledger and the on-device wallet balance.",
      "Document the case and monitor for recurrence."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Lite Payment Failed",
    "investigation_steps": [
      "Check UPI Lite payment transaction logs for the failure code.",
      "Verify if the UPI Lite wallet had sufficient balance for the payment.",
      "Confirm if the merchant's QR or VPA is compatible with UPI Lite payments.",
      "Check for any connectivity issues between the device and the UPI Lite service."
    ],
    "next_best_actions": [
      "If balance is insufficient, advise the customer-facing team to ask the customer to top up.",
      "If the merchant is not UPI Lite compatible, notify the merchant onboarding team to update compatibility.",
      "If a technical error, escalate to the UPI Lite tech team.",
      "Log the failure and track till resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Daily Limit Exceeded",
    "investigation_steps": [
      "Check the customer's UPI transaction log for the current day and total amount transacted.",
      "Verify the current UPI daily transaction limit set for the customer's account.",
      "Confirm if the limit is the NPCI-mandated limit or a bank-imposed lower limit.",
      "Check if a limit enhancement request is pending in the system."
    ],
    "next_best_actions": [
      "If the customer requires a higher limit, process a limit enhancement request per bank policy.",
      "Confirm the limit resets at midnight and the customer can transact after reset.",
      "If the bank limit is lower than NPCI's mandate, escalate to review the bank's limit policy.",
      "Communicate the limit details and enhancement process to the customer-facing team."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Transaction Limit Incorrect",
    "investigation_steps": [
      "Retrieve the current UPI transaction limit configuration for the customer's account.",
      "Cross-check the configured limit against NPCI's prescribed per-transaction limits.",
      "Verify if the limit was set correctly during account onboarding or was changed erroneously.",
      "Check for any recent system updates that may have altered transaction limits."
    ],
    "next_best_actions": [
      "Correct the transaction limit to the appropriate value as per NPCI guidelines and bank policy.",
      "Escalate to the UPI configuration team if a system update incorrectly altered limits.",
      "Audit other accounts for similar limit misconfigurations.",
      "Confirm the corrected limit is applied and test with a low-value transaction."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Limit Reset Delay",
    "investigation_steps": [
      "Check the UPI limit reset schedule in the bank's UPI management system.",
      "Confirm if the daily limit is set to reset at midnight and if the reset job is running on schedule.",
      "Review scheduled job logs for any failures or delays in the limit reset process.",
      "Verify if the delay is specific to one customer or systemic."
    ],
    "next_best_actions": [
      "If the reset job failed, escalate to the tech team to manually trigger the limit reset.",
      "Review the scheduled job configuration and fix any timing or dependency issues.",
      "Monitor the reset job over the next cycle to confirm regular operation.",
      "Manually reset the limit for the affected customer account while the systemic fix is applied."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Bank Limit Mismatch",
    "investigation_steps": [
      "Compare the UPI transaction limits configured in the bank's UPI switch with NPCI's permitted limits.",
      "Identify where the mismatch exists (per-transaction limit, daily limit, or per-beneficiary limit).",
      "Check if the mismatch is due to a recent policy change or a configuration error.",
      "Review if the mismatch is affecting multiple customers or is account-specific."
    ],
    "next_best_actions": [
      "Correct the limit configuration in the UPI switch to align with NPCI guidelines.",
      "If the mismatch is due to a bank policy change, escalate to the product/policy team for clarification.",
      "Audit all limit configurations across customer segments.",
      "Test and validate the corrected limits before implementing."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Unable to Add Bank Account",
    "investigation_steps": [
      "Check the bank account linking API logs for the error code returned.",
      "Verify if the account to be added is an eligible account type (savings, current) per NPCI rules.",
      "Confirm if the mobile number used for UPI matches the mobile number on the new account.",
      "Check if the new account is active and not frozen or under restriction."
    ],
    "next_best_actions": [
      "If mobile number mismatch, update the mobile number in CBS after verification.",
      "If the account is inactive, initiate reactivation and retry.",
      "If a system error, escalate to the UPI tech team for account linking fix.",
      "Confirm successful account addition after resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Unable to Remove Bank Account",
    "investigation_steps": [
      "Check the UPI account delink API logs for the failure reason.",
      "Verify if the account being removed is set as the primary account for UPI.",
      "Confirm if there are any pending transactions or mandates linked to the account.",
      "Check if the removal was attempted from an authorized device."
    ],
    "next_best_actions": [
      "If it is the primary account, assist in switching the primary account before removing.",
      "If pending mandates exist, cancel them first and then retry account removal.",
      "Escalate to the UPI tech team if the delink API is failing.",
      "Confirm account removal in the NPCI mapper after resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Primary Bank Account Not Updating",
    "investigation_steps": [
      "Check the UPI primary account update API logs for errors.",
      "Verify if the new primary account is correctly linked and active in NPCI mapper.",
      "Confirm if the update request was submitted from an authorized device.",
      "Check if there is a system delay in syncing the primary account change."
    ],
    "next_best_actions": [
      "If a sync delay, wait for the next mapper sync cycle and re-verify.",
      "If an API error, escalate to the UPI tech team.",
      "Manually update the primary account in the UPI switch if the system update fails.",
      "Confirm the update is reflected in NPCI mapper and the UPI app."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Bank Account Mapping Incorrect",
    "investigation_steps": [
      "Check the NPCI mapper for the current account-to-VPA mapping.",
      "Compare the mapping with the intended account and VPA in CBS.",
      "Identify when the incorrect mapping occurred (onboarding, account change, system update).",
      "Confirm if transactions were made to/from the wrong account due to the incorrect mapping."
    ],
    "next_best_actions": [
      "Correct the mapping in NPCI mapper and CBS immediately.",
      "If transactions were made to the wrong account, initiate reconciliation and reversal.",
      "Audit similar mapping records for systemic errors.",
      "Confirm corrected mapping with a test transaction."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Incorrect Account Selected for Payment",
    "investigation_steps": [
      "Retrieve the transaction record and check which account was debited.",
      "Verify if the customer's default/primary account was changed inadvertently.",
      "Check if the UPI app displayed the correct account options to the user.",
      "Confirm if the debit from the wrong account caused any financial issue (e.g., overdraft, insufficient balance)."
    ],
    "next_best_actions": [
      "If the wrong account was debited and the payment is complete, advise the customer-facing team on the next steps per bank policy.",
      "Review the UPI app account selection logic for any bugs and escalate to the mobile dev team if needed.",
      "Correct the primary account setting if it was changed incorrectly.",
      "Document and log the case for UX improvement review."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Multiple Bank Accounts Conflicting",
    "investigation_steps": [
      "List all bank accounts linked to the customer's UPI and check for conflicts in NPCI mapper.",
      "Identify which account is set as primary and whether conflicting mappings exist.",
      "Check if the conflict is causing incorrect debits or payment failures.",
      "Review CBS for any duplicate account registrations."
    ],
    "next_best_actions": [
      "Resolve the conflict by confirming the customer's intended primary account and removing incorrect mappings.",
      "Update the NPCI mapper to reflect the correct account-to-VPA mapping.",
      "Escalate to the UPI tech team if system-level conflicts are detected.",
      "Reconcile any erroneous transactions resulting from the conflict."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI ID Not Found",
    "investigation_steps": [
      "Search the NPCI mapper for the reported UPI ID and check its registration status.",
      "Verify if the UPI ID was ever registered or if it has been deregistered.",
      "Confirm if the UPI ID spelling is correct and there are no typographical errors.",
      "Check if the UPI ID belongs to the correct bank's handle."
    ],
    "next_best_actions": [
      "If the UPI ID was deregistered, investigate the reason and re-register if valid.",
      "If the UPI ID was never created, initiate registration.",
      "If the UPI ID belongs to another bank, direct the inquiry to the appropriate bank.",
      "Log the case and communicate the outcome to the relevant team."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Handle Not Recognized",
    "investigation_steps": [
      "Verify if the UPI handle (e.g., @bankname) is registered and operational in NPCI.",
      "Check NPCI's handle registry to confirm the handle's status.",
      "Identify if there is a typo in the handle or if the handle was recently changed.",
      "Confirm if the bank is experiencing a handle resolution outage."
    ],
    "next_best_actions": [
      "If the handle is misspelled, correct it in the transaction and retry.",
      "If the handle is inactive, escalate to NPCI to restore handle resolution.",
      "If a bank-level outage, escalate to the infra team for immediate fix.",
      "Test handle resolution after fix and confirm with a test transaction."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Invalid VPA",
    "investigation_steps": [
      "Validate the VPA format against NPCI's VPA standards.",
      "Search the NPCI mapper to confirm if the VPA exists and is active.",
      "Check for special characters, spaces, or incorrect formats in the reported VPA.",
      "Confirm if the VPA was recently deleted or deactivated."
    ],
    "next_best_actions": [
      "If the VPA format is incorrect, correct it and retry the transaction.",
      "If the VPA does not exist, advise the team to use the correct VPA or beneficiary account details.",
      "If the VPA was deactivated, investigate the reason and reactivate if appropriate.",
      "Log the invalid VPA case for pattern analysis."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "VPA Verification Failed",
    "investigation_steps": [
      "Check NPCI's VPA verification API response for the failure code.",
      "Confirm if the VPA being verified exists and is active in the NPCI mapper.",
      "Verify if the NPCI VPA verification service was available at the time of the check.",
      "Check for network connectivity issues between the UPI switch and NPCI."
    ],
    "next_best_actions": [
      "If a service outage, escalate to NPCI and retry verification once service is restored.",
      "If the VPA does not exist, advise using the correct VPA or beneficiary bank details.",
      "If connectivity is the issue, escalate to the network/infra team.",
      "Document the failure and retry outcome in the complaint system."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Beneficiary Verification Failed",
    "investigation_steps": [
      "Check NPCI's account verification (penny drop or name fetch) API response for the error code.",
      "Confirm if the beneficiary's account number and IFSC are correct.",
      "Verify if the beneficiary's bank is available and responding to verification requests.",
      "Check for any NPCI-level errors in the beneficiary verification service."
    ],
    "next_best_actions": [
      "If account details are incorrect, advise the team to correct and retry.",
      "If the beneficiary bank is unavailable, retry after the bank's service is restored.",
      "Escalate to NPCI if the verification service is experiencing systemic issues.",
      "Log the case and track verification retry outcomes."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Transaction History Not Available",
    "investigation_steps": [
      "Check the UPI transaction history service API for errors or downtime.",
      "Verify if the transaction history data is available in the core banking system.",
      "Confirm the date range requested and if it falls within the available data retention period.",
      "Check for any database or data sync issues affecting history retrieval."
    ],
    "next_best_actions": [
      "If the history API is down, escalate to the tech team for immediate restoration.",
      "If data retention limits are the issue, retrieve history from CBS or NPCI archives.",
      "Coordinate with the data team to restore history availability for affected accounts.",
      "Communicate expected resolution to the customer-facing team."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Transaction History Incorrect",
    "investigation_steps": [
      "Compare the displayed transaction history with the CBS records and NPCI settlement files.",
      "Identify specific discrepancies (missing transactions, incorrect amounts, wrong beneficiary).",
      "Check if the data is being fetched from the correct source and is mapped to the right account.",
      "Review if any recent system update affected the transaction history display logic."
    ],
    "next_best_actions": [
      "Correct the data display issue by fetching accurate records from CBS.",
      "Escalate to the UPI platform/tech team to fix the history display logic if it is a bug.",
      "Reconcile the displayed history with the CBS and NPCI records.",
      "Validate the fix with a quality check before deploying."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Passbook Not Updated",
    "investigation_steps": [
      "Verify if the UPI passbook sync service is operational.",
      "Check if recent UPI transactions are reflected in CBS but not in the passbook.",
      "Confirm if the passbook update is triggered in real-time or is batch-based.",
      "Review passbook sync job logs for failures or delays."
    ],
    "next_best_actions": [
      "Trigger a manual passbook sync for the affected account.",
      "If the sync job is failing, escalate to the tech team for a fix.",
      "Review the passbook update frequency and optimize if batch delays are causing complaints.",
      "Confirm passbook is updated after fix and matches CBS records."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Notification Not Received",
    "investigation_steps": [
      "Check the push notification delivery log for the customer's device/token.",
      "Verify if the customer's device has notifications enabled for the UPI app.",
      "Confirm if the notification was triggered by the UPI system after the transaction.",
      "Check for any issues with the push notification gateway (Firebase, APNS, etc.)."
    ],
    "next_best_actions": [
      "If the gateway failed, escalate to the notification vendor for investigation.",
      "If the device token is expired, refresh the device registration for notifications.",
      "Advise the customer-facing team to guide customers to re-enable notifications.",
      "Monitor notification delivery rates and escalate if failure rates are high."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "SMS Confirmation Not Received",
    "investigation_steps": [
      "Check the SMS gateway log to confirm if the transaction confirmation SMS was triggered.",
      "Verify the mobile number to which the SMS was sent and confirm it matches the registered number.",
      "Check for DND (Do Not Disturb) registration on the customer's number.",
      "Review the SMS delivery status (delivered, failed, pending) from the gateway."
    ],
    "next_best_actions": [
      "If the SMS was not triggered, escalate to the notification team to fix the triggering logic.",
      "If DND is active, advise the customer-facing team that transactional SMS should still be delivered; escalate to the telecom team if blocked.",
      "If the SMS gateway failed, escalate to the vendor for diagnosis.",
      "Ensure the SMS template and sender ID comply with TRAI regulations."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Payment Success but No Receipt Generated",
    "investigation_steps": [
      "Confirm the payment was completed successfully in NPCI and CBS.",
      "Check the receipt generation service logs for any errors at the time of payment.",
      "Verify if the receipt generation is triggered automatically post-payment.",
      "Confirm the receipt was generated but not delivered (e.g., email/push failure) vs not generated at all."
    ],
    "next_best_actions": [
      "Generate the payment receipt manually from CBS or the UPI transaction management system.",
      "Share the generated receipt via the appropriate customer communication channel.",
      "Escalate to the tech team if the auto-receipt generation service is down.",
      "Fix the receipt generation trigger and test with a sample transaction."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Payment Receipt Incorrect",
    "investigation_steps": [
      "Compare the receipt details with the actual transaction record in CBS and NPCI.",
      "Identify which fields are incorrect (amount, date, beneficiary, transaction ID).",
      "Check the receipt generation logic for data mapping errors.",
      "Confirm if the error is on a single receipt or across multiple receipts."
    ],
    "next_best_actions": [
      "Regenerate the correct receipt using accurate data from CBS and re-issue to the customer.",
      "Escalate to the tech team to fix the data mapping issue in the receipt generation service.",
      "Audit recent receipts for similar errors and proactively correct if needed.",
      "Test the corrected receipt generation with multiple transaction types."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Services Temporarily Unavailable",
    "investigation_steps": [
      "Check the bank's UPI switch and NPCI connectivity status.",
      "Review the UPI platform health dashboard for any outage indicators.",
      "Determine if the unavailability is planned maintenance or an unplanned outage.",
      "Check NPCI's operational status page for any system-wide notices."
    ],
    "next_best_actions": [
      "If unplanned, escalate to the infra and UPI ops teams for immediate restoration.",
      "Publish an internal incident advisory for all customer-facing teams.",
      "Activate business continuity protocols if the outage exceeds defined thresholds.",
      "Validate full service restoration with end-to-end transaction testing before declaring resolution."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Profile Update Failed",
    "investigation_steps": [
      "Check the UPI profile update API logs for the failure code.",
      "Verify if the update request data (name, preferred VPA, linked account) meets NPCI requirements.",
      "Confirm if the request was made from an authenticated and bound device.",
      "Check for any system errors in the profile management service."
    ],
    "next_best_actions": [
      "If validation errors, correct the data and retry the profile update.",
      "If system error, escalate to the UPI platform tech team.",
      "Manually update the profile in the UPI admin console if automated update is failing.",
      "Confirm profile update success in NPCI records."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "Mobile Number Change Not Reflected",
    "investigation_steps": [
      "Confirm the mobile number change was updated in CBS.",
      "Check if the NPCI mapper has been updated with the new mobile number.",
      "Review the sync process between CBS and NPCI mapper for the mobile number update.",
      "Verify if the change is blocked due to a pending validation or KYC requirement."
    ],
    "next_best_actions": [
      "Trigger a manual sync of the mobile number update from CBS to the NPCI mapper.",
      "If a KYC block exists, resolve it first and then resync.",
      "Confirm the new mobile number is reflected in the NPCI mapper and the UPI app.",
      "Escalate to the tech team if the sync process is failing systematically."
    ]
  },
  {
    "major_issue": "UPI",
    "sub_issue": "UPI Account Deactivation Failed",
    "investigation_steps": [
      "Check the UPI account deactivation API logs for the failure reason.",
      "Confirm if there are pending transactions, mandates, or active collect requests on the account.",
      "Verify if the deactivation request was submitted through an authorized channel.",
      "Review any system errors in the UPI deactivation workflow."
    ],
    "next_best_actions": [
      "Resolve any pending transactions or cancel active mandates before retrying deactivation.",
      "Escalate to the UPI tech team if system errors are preventing deactivation.",
      "Manually deactivate the UPI account in the UPI admin console if automated deactivation fails.",
      "Confirm deactivation in NPCI records and update CBS accordingly."
    ]
  }
],

"major_issue" = "Credit Card"

sub_issues_data = [
    {
        "sub_issue": "Card Lost",
        "investigation_steps": [
            "Verify the customer's identity and confirm card details from the CBS/card management system.",
            "Check the date and time the customer reported the card as lost.",
            "Review recent transactions on the card to identify any unauthorized activity post-loss.",
            "Confirm the card's current status (active, blocked, or already reported lost) in the card management system.",
            "Check if a card block or hotlisting was already triggered by the customer via any channel."
        ],
        "next_best_actions": [
            "Immediately hotlist/block the lost card in the card management system to prevent misuse.",
            "Initiate a replacement card request and set the delivery address as per CBS records.",
            "Flag all transactions post the reported loss time for fraud review.",
            "Notify the fraud monitoring team to place enhanced surveillance on the account.",
            "Update the complaint management system with the block confirmation and replacement card dispatch details."
        ]
    },
    {
        "sub_issue": "Card Stolen",
        "investigation_steps": [
            "Verify the customer's identity and confirm the card details in the card management system.",
            "Identify the time the theft is reported and review all transactions after that time.",
            "Check fraud monitoring alerts for any activity on the stolen card.",
            "Review recent transaction patterns for any suspicious activity that may have preceded the theft.",
            "Confirm if the card was hotlisted by any automated fraud detection system already."
        ],
        "next_best_actions": [
            "Immediately hotlist the card in the card management system.",
            "Initiate a replacement card order and confirm the delivery address.",
            "Route all post-theft transactions for fraud investigation and chargeback processing.",
            "File an internal fraud incident report and coordinate with the fraud investigation team.",
            "Advise the branch/ops team to guide the customer to file a police report, which may be required for chargeback processing."
        ]
    },
    {
        "sub_issue": "Unauthorized Transaction",
        "investigation_steps": [
            "Retrieve the transaction details (amount, merchant, date, mode) from the card transaction system.",
            "Verify whether the card was in the customer's possession at the time of the transaction.",
            "Check if 3D Secure (OTP) authentication was used for online transactions.",
            "Review device, IP, and geolocation metadata associated with the transaction.",
            "Cross-check with fraud monitoring alerts for the account at the time of the transaction."
        ],
        "next_best_actions": [
            "Block the card immediately to prevent further unauthorized transactions.",
            "Initiate a chargeback request for the disputed transaction as per network (Visa/Mastercard/RuPay) timelines.",
            "Escalate to the fraud investigation team for a full forensic review.",
            "Raise a dispute with the card network and provide all transaction evidence.",
            "Provisionally credit the disputed amount to the customer's account if confirmed unauthorized, per bank policy."
        ]
    },
    {
        "sub_issue": "Fraudulent Transaction",
        "investigation_steps": [
            "Pull the complete transaction record including merchant details, terminal ID, and authorization code.",
            "Confirm whether card-present or card-not-present fraud occurred.",
            "Check if the card was physically used while the customer was in a different location.",
            "Review fraud scoring for the transaction and confirm if the fraud model flagged it.",
            "Identify whether OTP/CVV2 was used and confirm if it was intercepted."
        ],
        "next_best_actions": [
            "Hotlist the card immediately and issue a replacement.",
            "File a chargeback with the acquiring bank through the card network.",
            "Initiate the internal fraud investigation process and document all evidence.",
            "Report the fraudulent transaction to the card network (Visa/Mastercard/RuPay) fraud desk.",
            "Provisionally credit the disputed amount to the customer as per RBI guidelines and bank policy."
        ]
    },
    {
        "sub_issue": "Fraudulent International Transaction",
        "investigation_steps": [
            "Retrieve the international transaction details including merchant country, currency, and amount.",
            "Verify if the customer had enabled international transactions on their card.",
            "Check if the transaction was 3D Secure authenticated.",
            "Review the customer's travel history and check if the transaction location is inconsistent.",
            "Cross-reference with fraud monitoring for any geolocation mismatch alerts."
        ],
        "next_best_actions": [
            "Block the card and disable international transaction capability pending investigation.",
            "Initiate an international chargeback through the card network per prescribed timelines.",
            "Escalate to the cross-border fraud investigation team.",
            "Report the fraud to the card network's international fraud desk.",
            "Provisionally credit the disputed amount and update the complaint management system."
        ]
    },
    {
        "sub_issue": "Card Compromised",
        "investigation_steps": [
            "Verify if the compromise alert was generated internally or reported by the customer or card network.",
            "Check the card's recent transaction history for any suspicious activity.",
            "Identify the potential compromise point (data breach, skimming, phishing).",
            "Confirm if the card details (PAN, CVV, expiry) were exposed.",
            "Review fraud monitoring alerts linked to the compromised card."
        ],
        "next_best_actions": [
            "Proactively hotlist the compromised card immediately.",
            "Issue a replacement card with a new card number and CVV.",
            "Initiate chargeback for any fraudulent transactions identified on the compromised card.",
            "Report the compromise to the card network and update the fraud intelligence database.",
            "Conduct a post-compromise audit of all transactions for the past 60–90 days."
        ]
    },
    {
        "sub_issue": "Card Cloned",
        "investigation_steps": [
            "Retrieve transaction logs to identify suspicious card-present transactions at unusual locations.",
            "Verify if the customer was physically present at the merchant location at the time of the cloned transaction.",
            "Check if the card has a chip (EMV) — cloning is more likely for magnetic stripe transactions.",
            "Review ATM/POS terminal logs where the card was recently used for evidence of skimming.",
            "Cross-reference with the fraud monitoring database for known skimming locations."
        ],
        "next_best_actions": [
            "Immediately hotlist the cloned card and issue a replacement with EMV chip.",
            "Initiate chargebacks for all transactions identified as resulting from the cloned card.",
            "Report the suspected skimming terminal to the acquiring bank and card network.",
            "Escalate to the fraud investigation team for a full card cloning inquiry.",
            "File a report with law enforcement and document all findings."
        ]
    },
    {
        "sub_issue": "Card Misused",
        "investigation_steps": [
            "Retrieve the transactions reported as misuse from the card transaction system.",
            "Confirm if the card was in the customer's possession or shared with a known party.",
            "Review authorization details (PIN-based, signature, OTP) for each disputed transaction.",
            "Check if the misuse is by an authorized add-on cardholder or an unauthorized party.",
            "Cross-reference with fraud monitoring and chargeback management systems."
        ],
        "next_best_actions": [
            "Block the card if misuse by an unknown party is confirmed.",
            "Initiate chargeback for transactions identified as unauthorized misuse.",
            "If misuse is by an add-on cardholder, review account terms and escalate to legal/compliance.",
            "Coordinate with the fraud team to classify misuse type and take appropriate recovery action.",
            "Update the complaint management system with investigation findings."
        ]
    },
    {
        "sub_issue": "Suspicious Transaction",
        "investigation_steps": [
            "Retrieve the flagged transaction details from the transaction monitoring system.",
            "Check the fraud scoring model output and the reason for the suspicious flag.",
            "Review transaction pattern deviations — new merchant, unusual amount, atypical location.",
            "Verify whether the transaction was 3D Secure authenticated.",
            "Confirm if a similar transaction was flagged previously on the same account."
        ],
        "next_best_actions": [
            "Place a temporary transaction hold or block pending confirmation.",
            "Initiate verification with the customer-facing team via secure channel to confirm or deny the transaction.",
            "If confirmed fraudulent, block the card and initiate chargeback.",
            "Update the fraud monitoring rule set if this represents a new fraud pattern.",
            "Document the investigation findings in the fraud case management system."
        ]
    },
    {
        "sub_issue": "Card Blocked Without Notice",
        "investigation_steps": [
            "Retrieve the card block record from the card management system and identify who triggered the block.",
            "Check if the block was triggered by the fraud monitoring system, risk team, or an automated rule.",
            "Review the trigger reason (suspicious activity, credit risk flag, regulatory hold, inactivity).",
            "Confirm if the customer was notified via SMS, email, or any other communication before the block.",
            "Verify if the block is in compliance with RBI guidelines on customer notification."
        ],
        "next_best_actions": [
            "If the block was in error, immediately unblock the card after verification.",
            "If the block was for fraud/risk reasons, confirm with the relevant team before unblocking.",
            "Issue a formal internal communication to the customer notification team about the missed alert.",
            "Review the automated block notification process and fix gaps.",
            "Document the block reason and action taken in the CRM."
        ]
    },
    {
        "sub_issue": "Card Block Request Not Processed",
        "investigation_steps": [
            "Verify if the customer's block request was received and logged in the complaint management system.",
            "Check the card management system to confirm if the block was applied.",
            "Review IVR, app, and branch logs for the customer's block request.",
            "Identify the failure point — reception, processing, or system error.",
            "Confirm if any transactions occurred on the card after the block request was made."
        ],
        "next_best_actions": [
            "Immediately block the card in the card management system.",
            "Initiate chargeback for any unauthorized transactions that occurred after the block request was logged.",
            "Escalate the failure to block to the card ops team for root cause analysis.",
            "Fix the system or process gap that prevented the block from being applied.",
            "Update the complaint system with the block confirmation and transaction review outcome."
        ]
    },
    {
        "sub_issue": "Card Unblocking Delay",
        "investigation_steps": [
            "Retrieve the unblock request log from the card management system.",
            "Identify the reason the card was originally blocked.",
            "Confirm if all prerequisites for unblocking (identity verification, clearance of risk flag) have been met.",
            "Review SLA timelines for card unblocking and identify the delay point."
        ],
        "next_best_actions": [
            "Process the card unblock immediately if all conditions are met.",
            "If a pending verification is causing delay, escalate to the relevant team for priority resolution.",
            "Update the customer-facing team with the unblock confirmation.",
            "Review and streamline the unblocking process to meet SLA."
        ]
    },
    {
        "sub_issue": "Card Hotlisting Failed",
        "investigation_steps": [
            "Check the card management system for the hotlisting request log and error code.",
            "Confirm if the hotlisting API or service experienced a system error.",
            "Verify if the card was hotlisted in the card network's (Visa/Mastercard/RuPay) system.",
            "Identify the exact point of failure — internal system or card network communication."
        ],
        "next_best_actions": [
            "Retry the hotlisting immediately through an alternative channel or manual override.",
            "If the card cannot be hotlisted via the system, contact the card network directly for emergency hotlisting.",
            "Review transactions post-hotlisting failure for any fraudulent activity.",
            "Escalate the technical failure to the card management platform team for immediate fix.",
            "Document the failure and manual steps taken in the incident management system."
        ]
    },
    {
        "sub_issue": "Card Replacement Delay",
        "investigation_steps": [
            "Check the card replacement request date and current status in the card management system.",
            "Verify if the replacement card was produced and dispatched by the card production vendor.",
            "Track the courier/delivery status using the dispatch reference number.",
            "Identify the delay point — production, dispatch, or delivery."
        ],
        "next_best_actions": [
            "Coordinate with the card production team and courier vendor to expedite delivery.",
            "If the card is in transit, provide the expected delivery date to the customer-facing team.",
            "If the card is lost in transit, re-initiate the replacement card request.",
            "Issue a temporary virtual card if the bank's system supports it to mitigate the customer's inconvenience.",
            "Update the complaint management system with the new expected delivery date."
        ]
    },
    {
        "sub_issue": "Replacement Card Not Received",
        "investigation_steps": [
            "Confirm the dispatch date and courier tracking details for the replacement card.",
            "Verify if the delivery address used matches the customer's current address in CBS.",
            "Check the courier status for delivery attempts, returns, or failed deliveries.",
            "Confirm if the card was returned to the bank by the courier."
        ],
        "next_best_actions": [
            "If the card was not delivered, re-initiate card production and dispatch to the correct address.",
            "If the address was incorrect, update the address in CBS and reorder the card.",
            "If the card is returned to bank, arrange re-delivery or branch pickup.",
            "Hotlist the undelivered card to prevent misuse if it is unaccounted for.",
            "Track the new dispatch and confirm delivery in the complaint system."
        ]
    },
    {
        "sub_issue": "Card Renewal Delay",
        "investigation_steps": [
            "Check the card's expiry date and confirm if the auto-renewal was triggered in the card management system.",
            "Verify if the renewal card production was initiated and the expected dispatch date.",
            "Review if there are any account-level flags (delinquency, risk hold) preventing auto-renewal.",
            "Confirm the delivery address in CBS is current."
        ],
        "next_best_actions": [
            "If renewal was not triggered, manually initiate the renewal card production.",
            "If renewal was triggered but not dispatched, coordinate with the card production team.",
            "If account flags are blocking renewal, escalate to the credit/risk team for review.",
            "Communicate the expected delivery date to the customer-facing team.",
            "Update the complaint system with the renewal card tracking details."
        ]
    },
    {
        "sub_issue": "Renewed Card Not Received",
        "investigation_steps": [
            "Retrieve the dispatch date and courier tracking number for the renewed card.",
            "Check the delivery status including any failed attempts or returns.",
            "Verify the delivery address used for the renewed card.",
            "Confirm if the renewed card was returned to the bank."
        ],
        "next_best_actions": [
            "If delivery failed, coordinate with the courier to redeliver or arrange branch pickup.",
            "If the address is incorrect, update CBS and reorder the renewed card.",
            "If the card is missing in transit, hotlist it and reorder.",
            "Escalate to the card production and logistics team for priority reissue.",
            "Track and confirm delivery of the reordered card."
        ]
    },
    {
        "sub_issue": "Card Activation Failed",
        "investigation_steps": [
            "Check the card activation service logs for the failure code.",
            "Verify if the card number, expiry, and CVV entered during activation are correct.",
            "Confirm the card is in a pre-activation state in the card management system.",
            "Check if the activation was attempted via IVR, app, or net banking and identify the failure point.",
            "Verify if the customer's registered mobile number is correctly mapped for OTP-based activation."
        ],
        "next_best_actions": [
            "Retry activation via the bank's admin console after confirming card details.",
            "If the activation service is down, escalate to the tech team for immediate fix.",
            "Manually activate the card from the card management system if the self-service channel fails.",
            "Confirm successful activation and update the complaint system."
        ]
    },
    {
        "sub_issue": "Card Activation Pending",
        "investigation_steps": [
            "Check the card management system for the activation request status.",
            "Identify if activation is pending due to a system queue, KYC verification, or risk review.",
            "Review the activation request timestamp and check against the expected SLA.",
            "Confirm if all required customer actions (e.g., OTP verification) were completed."
        ],
        "next_best_actions": [
            "Escalate the pending activation to the card ops team for priority processing.",
            "If pending due to KYC, coordinate with the KYC team to clear the verification.",
            "Manually activate the card if all prerequisites are met.",
            "Update the complaint system with activation confirmation."
        ]
    },
    {
        "sub_issue": "Card Not Activated",
        "investigation_steps": [
            "Confirm the card's current status in the card management system.",
            "Check if an activation request was ever received from the customer.",
            "Verify the card was issued and received by the customer.",
            "Confirm if there is any account-level restriction preventing activation."
        ],
        "next_best_actions": [
            "Initiate the card activation process after verifying customer identity.",
            "If an account restriction exists, investigate and resolve before activating.",
            "If the card was never received, reissue and then activate.",
            "Confirm successful activation and log in the complaint system."
        ]
    },
    {
        "sub_issue": "Card PIN Generation Failed",
        "investigation_steps": [
            "Check the PIN generation service logs for the failure code.",
            "Verify if the HSM (Hardware Security Module) and PIN block service are operational.",
            "Confirm the customer's debit card or registered mobile is correctly linked for PIN generation.",
            "Check if the failure is channel-specific (IVR, app, ATM)."
        ],
        "next_best_actions": [
            "Retry PIN generation from the bank's admin console after root cause identification.",
            "If HSM is down, escalate to the infra team as a P1 incident.",
            "Manually trigger PIN generation through the card management platform.",
            "Confirm PIN delivery (via SMS, mailer, or app) and update the complaint system."
        ]
    },
    {
        "sub_issue": "Card PIN Reset Failed",
        "investigation_steps": [
            "Check PIN reset service logs for the error code.",
            "Verify if the customer completed all authentication steps (OTP, biometric, security question).",
            "Confirm the card is active and not blocked.",
            "Check HSM and PIN reset service availability."
        ],
        "next_best_actions": [
            "Retry the PIN reset from the bank's admin console.",
            "If service is down, escalate to the infra/security team.",
            "Manually reset the PIN after identity verification if self-service fails.",
            "Confirm the new PIN is set and operational."
        ]
    },
    {
        "sub_issue": "PIN Not Received",
        "investigation_steps": [
            "Confirm whether the PIN was dispatched via post (PIN mailer), SMS, or app notification.",
            "Check the dispatch date and delivery status for postal PIN mailers.",
            "For SMS-based PINs, check the SMS gateway delivery log and the registered mobile number.",
            "Confirm if the PIN was received on the correct channel and not filtered."
        ],
        "next_best_actions": [
            "If PIN mailer is lost in transit, initiate regeneration and re-dispatch.",
            "If SMS PIN was not delivered, check the SMS gateway and resend.",
            "For online PIN display, check if the app/net banking session was active when the PIN was generated.",
            "Confirm successful PIN receipt and log in the complaint system."
        ]
    },
    {
        "sub_issue": "Forgot PIN Assistance",
        "investigation_steps": [
            "Verify the customer's identity using registered contact details and KYC data.",
            "Confirm the card is active and in good standing.",
            "Check the customer's last PIN change and whether a cooling-off period applies."
        ],
        "next_best_actions": [
            "Initiate the secure PIN reset process after identity verification.",
            "Generate a new PIN via the appropriate channel (IVR, app, ATM, or admin console).",
            "Ensure the new PIN is delivered securely to the customer via the registered channel.",
            "Log the PIN reset in the card management system."
        ]
    },
    {
        "sub_issue": "Incorrect PIN Accepted",
        "investigation_steps": [
            "Retrieve the transaction authorization log to confirm the PIN verification result.",
            "Check if the HSM PIN validation process returned an incorrect success response.",
            "Review the POS terminal or ATM logs for the transaction.",
            "Confirm if the card uses a magnetic stripe or EMV chip, as this affects PIN validation."
        ],
        "next_best_actions": [
            "Escalate to the card security team and HSM provider for immediate investigation.",
            "If a PIN validation flaw is confirmed, conduct a full security audit.",
            "Report the incident to the card network (Visa/Mastercard/RuPay) for investigation.",
            "Monitor the affected card and account for further suspicious activity.",
            "Document as a critical security incident and escalate to compliance and CISO."
        ]
    },
    {
        "sub_issue": "Card Swipe Failed",
        "investigation_steps": [
            "Confirm the card's status (active, not blocked) in the card management system.",
            "Check if the magnetic stripe on the card is damaged.",
            "Review the POS terminal logs at the merchant for any error codes.",
            "Verify if the failure was at a specific merchant or across all terminals."
        ],
        "next_best_actions": [
            "If the card's magnetic stripe is damaged, initiate a replacement card.",
            "If the issue is terminal-specific, coordinate with the merchant's acquiring bank.",
            "Check if the card is enabled for swipe transactions and update if needed.",
            "Confirm issue resolution and update the complaint system."
        ]
    },
    {
        "sub_issue": "Contactless Payment Not Working",
        "investigation_steps": [
            "Confirm if the contactless (NFC) feature is enabled on the card in the card management system.",
            "Check if the contactless transaction limit is set and within the transacted amount.",
            "Review the POS terminal for NFC compatibility and reader functionality.",
            "Confirm if the card's NFC antenna is intact (not damaged)."
        ],
        "next_best_actions": [
            "If NFC is disabled, enable it in the card management system.",
            "If the card is damaged, initiate a replacement.",
            "Coordinate with the merchant's acquiring bank if the terminal is non-functional.",
            "Test contactless payment after fix and confirm resolution."
        ]
    },
    {
        "sub_issue": "Tap to Pay Failed",
        "investigation_steps": [
            "Confirm that the card's contactless feature is active.",
            "Check the transaction amount vs. the contactless limit configured on the card.",
            "Review the POS terminal for NFC reader issues.",
            "Confirm if the failure is card-specific or merchant-terminal-specific."
        ],
        "next_best_actions": [
            "If the contactless limit is too low, update the limit in the card management system.",
            "If the card is faulty, issue a replacement.",
            "Escalate terminal issues to the acquiring bank.",
            "Confirm resolution and log in the complaint system."
        ]
    },
    {
        "sub_issue": "Card Declined at POS",
        "investigation_steps": [
            "Retrieve the decline reason code from the transaction authorization system.",
            "Check the card's current status, available credit limit, and any active restrictions.",
            "Confirm if the merchant's POS terminal was functioning correctly.",
            "Review if any fraud rule or velocity check triggered the decline."
        ],
        "next_best_actions": [
            "If declined due to limit, review and update the credit limit if eligible.",
            "If declined due to a fraud rule, review the rule trigger with the fraud ops team.",
            "If the decline was in error, clear the restriction and confirm card functionality.",
            "Coordinate with the merchant's acquiring bank if the decline was terminal-related."
        ]
    },
    {
        "sub_issue": "Online Card Transaction Failed",
        "investigation_steps": [
            "Retrieve the transaction failure code from the payment gateway and card authorization logs.",
            "Verify if the card is enabled for online transactions.",
            "Confirm if 3D Secure (OTP) authentication was completed successfully.",
            "Check if the billing address entered matched the registered address.",
            "Review if the merchant's payment gateway had any issues at the time."
        ],
        "next_best_actions": [
            "If online transactions are disabled, enable them per the customer's request.",
            "If OTP delivery failed, escalate to the SMS gateway team.",
            "If a merchant gateway issue, advise the customer-facing team to ask the customer to retry or use an alternate method.",
            "Confirm the card can process online transactions successfully after fix."
        ]
    },
    {
        "sub_issue": "International Transaction Declined",
        "investigation_steps": [
            "Confirm if international transactions are enabled on the card.",
            "Retrieve the decline reason code from the authorization system.",
            "Check if the transaction currency and country are on any restricted list.",
            "Review if a fraud rule for international transactions triggered the decline.",
            "Confirm if the customer was traveling or had notified the bank of international use."
        ],
        "next_best_actions": [
            "Enable international transactions if the customer has provided authorization.",
            "If declined due to fraud rule, review with the fraud ops team and whitelist if legitimate.",
            "If the decline is due to currency restriction, update the card's transaction profile.",
            "Confirm the card can process international transactions after fix."
        ]
    },
    {
        "sub_issue": "Domestic Transaction Declined",
        "investigation_steps": [
            "Retrieve the decline reason code from the authorization system.",
            "Verify the card's status, available credit limit, and active restrictions.",
            "Check if the transaction type (POS, online, ATM) is enabled on the card.",
            "Review fraud monitoring alerts at the time of the decline."
        ],
        "next_best_actions": [
            "Resolve the root cause — clear the restriction, top up credit limit eligibility, or fix the rule trigger.",
            "Confirm the card can transact domestically after fix.",
            "If the decline was due to a bank error, document and escalate for process review.",
            "Update the complaint system with the root cause and resolution."
        ]
    },
    {
        "sub_issue": "E-commerce Transaction Failed",
        "investigation_steps": [
            "Retrieve the failure code from the payment gateway and issuer authorization logs.",
            "Verify that the card is enabled for e-commerce transactions.",
            "Confirm if the OTP was delivered and entered correctly.",
            "Check if the merchant is registered on the card network and is a valid e-commerce merchant.",
            "Review any issuer-side fraud rules that may have blocked the transaction."
        ],
        "next_best_actions": [
            "Enable e-commerce transactions if disabled.",
            "If OTP delivery failed, escalate to the SMS gateway team.",
            "If a fraud rule blocked the transaction erroneously, review and whitelist.",
            "Coordinate with the payment gateway if the failure is on the merchant side.",
            "Confirm the card works for e-commerce post-fix."
        ]
    },
    {
        "sub_issue": "Recurring Payment Failed",
        "investigation_steps": [
            "Retrieve the recurring payment instruction details and check the failure code from the authorization system.",
            "Verify if the card is enabled for recurring transactions and the mandate is active.",
            "Confirm the card's available credit limit was sufficient at the time of the payment.",
            "Check if the merchant's subscription mandate has expired or was cancelled.",
            "Review if any account-level restriction blocked the recurring payment."
        ],
        "next_best_actions": [
            "If the mandate is expired, coordinate with the merchant and customer team to re-register.",
            "If the card limit was insufficient, review and update the limit if eligible.",
            "If a restriction blocked the payment, investigate and lift if appropriate.",
            "Retry the payment if within the permissible retry window.",
            "Update the mandate management system and the complaint system."
        ]
    },
    {
        "sub_issue": "Merchant Payment Failed",
        "investigation_steps": [
            "Retrieve the payment failure reason code from the card authorization logs.",
            "Confirm the merchant's terminal or payment gateway was operational.",
            "Check card status, credit limit, and transaction type enablement.",
            "Review fraud or risk rules that may have blocked the payment."
        ],
        "next_best_actions": [
            "Resolve the root cause (limit, block, rule trigger) and confirm card is functional.",
            "Coordinate with the merchant's acquiring bank if the issue is on the acceptance side.",
            "If the customer was charged despite the failed payment, initiate reversal.",
            "Log and track the complaint to closure."
        ]
    },
    {
        "sub_issue": "Payment Pending",
        "investigation_steps": [
            "Retrieve the payment transaction reference and check the status in the card processing system.",
            "Confirm if the authorization was approved but settlement is pending.",
            "Check if the merchant has submitted the settlement/clearing file.",
            "Review the settlement cycle and expected posting date."
        ],
        "next_best_actions": [
            "If within normal settlement timelines, monitor and confirm in the next cycle.",
            "If beyond SLA, escalate to the settlement/reconciliation team.",
            "Coordinate with the merchant's acquiring bank for settlement status.",
            "Update the complaint system once the payment is confirmed settled."
        ]
    },
    {
        "sub_issue": "Payment Not Reflected",
        "investigation_steps": [
            "Check the card account's transaction ledger for the payment credit.",
            "Verify if the payment was made via NEFT, NACH, or online banking and trace the payment reference.",
            "Confirm if the payment was received and posted in the card management system.",
            "Check for any float or clearing delays in the payment processing pipeline."
        ],
        "next_best_actions": [
            "Trace the payment through the reconciliation team and apply the credit to the card account.",
            "If the payment is stuck in clearing, escalate to the payments operations team.",
            "Confirm the credit is reflected in the card account and reduce the outstanding balance accordingly.",
            "Update the complaint system with the payment posting confirmation."
        ]
    },
    {
        "sub_issue": "Amount Debited but Payment Failed",
        "investigation_steps": [
            "Retrieve the transaction ID and confirm the debit in the customer's account/card ledger.",
            "Check the card network authorization log for the payment status.",
            "Determine if the debit was reversed or if a pending reversal is expected.",
            "Confirm whether the merchant received the payment despite the failure message."
        ],
        "next_best_actions": [
            "If the amount was debited and payment did not go through, initiate a reversal or refund.",
            "If a reversal is expected, monitor within the prescribed timeline and escalate if delayed.",
            "Raise a dispute with the card network if merchant settlement confirms no credit.",
            "Update the complaint system with the reversal reference and timeline."
        ]
    },
    {
        "sub_issue": "Amount Debited but Merchant Not Credited",
        "investigation_steps": [
            "Confirm the debit on the cardholder's account and retrieve the authorization code.",
            "Check if the acquiring bank received the settlement instruction for the transaction.",
            "Verify with the merchant's acquiring bank if the credit was applied.",
            "Review NPCI or card network settlement files for the transaction."
        ],
        "next_best_actions": [
            "If the merchant was not credited, initiate a manual credit to the merchant via the acquiring bank.",
            "Raise a dispute with the card network for settlement resolution.",
            "Coordinate between the issuing bank reconciliation team and acquiring bank.",
            "Confirm merchant credit and close the complaint."
        ]
    },
    {
        "sub_issue": "Duplicate Transaction",
        "investigation_steps": [
            "Retrieve all transaction records for the reported date and merchant and compare authorization codes.",
            "Confirm if two separate authorization requests were generated or one was double-posted.",
            "Check the card switch idempotency and de-duplication logic.",
            "Verify CBS entries to confirm the number of debits."
        ],
        "next_best_actions": [
            "Initiate a chargeback for the duplicate transaction.",
            "Coordinate with the merchant's acquiring bank to confirm settlement of both transactions.",
            "Credit the duplicate amount back to the cardholder's account.",
            "Escalate to the card platform team if duplication was caused by a system bug."
        ]
    },
    {
        "sub_issue": "Duplicate Debit",
        "investigation_steps": [
            "Retrieve CBS debit entries and match each against card network transaction references.",
            "Determine if two NPCI/network requests were generated or one request was double-posted.",
            "Review the card switch for duplicate transaction handling logic.",
            "Confirm if the merchant received the duplicate settlement."
        ],
        "next_best_actions": [
            "Reverse the duplicate debit from the card account.",
            "File a chargeback or reversal request with the card network.",
            "Update reconciliation records to reflect the corrected balance.",
            "Notify the fraud and tech teams if duplicate debits are systemic."
        ]
    },
    {
        "sub_issue": "Double Charge on Same Transaction",
        "investigation_steps": [
            "Retrieve both charge records and match them to card network authorization codes.",
            "Confirm whether the merchant submitted two authorization requests or one was duplicated.",
            "Check if the POS terminal sent the request twice due to a connectivity issue.",
            "Verify the merchant's settlement file for the number of transactions claimed."
        ],
        "next_best_actions": [
            "Initiate a chargeback for the extra charge via the card network.",
            "Coordinate with the merchant's acquirer to adjust the settlement.",
            "Credit the excess charge to the cardholder's account.",
            "Report the pattern to the fraud team if this merchant has multiple such occurrences."
        ]
    },
    {
        "sub_issue": "Refund Not Received",
        "investigation_steps": [
            "Confirm with the merchant's acquiring bank that the refund was initiated.",
            "Check the card network's refund transaction log for the refund reference.",
            "Verify if the refund credit was posted to the card account in the card management system.",
            "Confirm the refund was directed to the correct card number."
        ],
        "next_best_actions": [
            "If refund was initiated but not posted, trace through the card network and apply credit.",
            "If refund was not initiated, coordinate with the merchant's acquirer.",
            "Escalate to the card network if the refund is stuck in the network.",
            "Confirm credit posting and update the complaint system."
        ]
    },
    {
        "sub_issue": "Refund Delayed",
        "investigation_steps": [
            "Confirm the refund initiation date and compare with card network refund timelines.",
            "Retrieve the refund transaction ID and track its status in the card processing system.",
            "Verify if the delay is at the merchant, card network, or issuing bank end.",
            "Confirm if there is a batch delay in the settlement/refund cycle."
        ],
        "next_best_actions": [
            "If beyond SLA, escalate to the card network's operations team.",
            "Coordinate with the merchant's acquiring bank to confirm refund dispatch.",
            "Expedite the credit to the card account if funds are confirmed received at the bank.",
            "Set a follow-up task in the CRM to track until credit confirmation."
        ]
    },
    {
        "sub_issue": "Merchant Refund Pending",
        "investigation_steps": [
            "Verify with the merchant's acquiring bank whether the refund has been initiated.",
            "Confirm the merchant acknowledged the return/cancellation that triggered the refund.",
            "Review the merchant's refund SLA and check for compliance.",
            "Confirm the card network has not received any refund instruction from the merchant."
        ],
        "next_best_actions": [
            "Follow up with the merchant's acquirer to expedite the refund initiation.",
            "If the merchant is non-cooperative, initiate a chargeback process.",
            "Track the refund pending case in the dispute management system with deadlines.",
            "Confirm the refund is posted to the cardholder's account once received."
        ]
    },
    {
        "sub_issue": "Chargeback Not Processed",
        "investigation_steps": [
            "Verify if the chargeback request was submitted within the allowable dispute window per card network rules.",
            "Check the chargeback management system for the request status.",
            "Confirm all required documentation was submitted (transaction proof, customer declaration).",
            "Review if the chargeback was received and acknowledged by the card network."
        ],
        "next_best_actions": [
            "If documentation is incomplete, complete and resubmit the chargeback.",
            "Escalate to the chargeback management team for manual processing.",
            "Coordinate with the card network's dispute resolution desk.",
            "Track the chargeback to resolution in the dispute management system."
        ]
    },
    {
        "sub_issue": "Chargeback Rejected",
        "investigation_steps": [
            "Retrieve the chargeback rejection reason from the card network.",
            "Review the documentation submitted for the chargeback to identify gaps.",
            "Confirm if the rejection was due to timeline non-compliance or insufficient evidence.",
            "Check if the merchant submitted a compelling evidence response."
        ],
        "next_best_actions": [
            "If the rejection is contestable, prepare and file a pre-arbitration with additional evidence.",
            "If the rejection is final and valid, communicate the outcome to the relevant team.",
            "If the rejection is due to a process gap, improve documentation for future cases.",
            "Escalate to the card network arbitration process if the dispute is still valid."
        ]
    },
    {
        "sub_issue": "Dispute Resolution Delay",
        "investigation_steps": [
            "Retrieve the dispute case ID and check its current stage in the chargeback management system.",
            "Identify the delay point — internal review, card network review, or merchant response.",
            "Confirm if all required information has been submitted to the card network.",
            "Review the card network's prescribed timelines and check for SLA breach."
        ],
        "next_best_actions": [
            "Escalate the delayed dispute to the card network's operations team.",
            "If awaiting merchant response, follow up through the acquirer.",
            "Provisionally credit the disputed amount if delay exceeds the bank's internal SLA.",
            "Track the dispute to resolution and update the complaint system."
        ]
    },
    {
        "sub_issue": "Wrong Billing",
        "investigation_steps": [
            "Retrieve the billing statement and compare each transaction with CBS and card network records.",
            "Identify specific transactions that are incorrectly billed.",
            "Check if the wrong billing is due to data entry errors, system errors, or unauthorized transactions.",
            "Confirm the billing period and cycle used for the statement."
        ],
        "next_best_actions": [
            "Correct the billing in the card management system for verified errors.",
            "If unauthorized transactions are found, initiate chargeback.",
            "Issue a revised statement after corrections.",
            "Log the billing error in the complaint system and escalate to the billing team."
        ]
    },
    {
        "sub_issue": "Billing Dispute",
        "investigation_steps": [
            "Review the disputed transaction(s) in the card management system.",
            "Confirm the merchant details, transaction amount, and authorization code.",
            "Check if the customer has proof (receipt, cancellation confirmation) for the dispute.",
            "Identify whether the dispute is for unauthorized transactions, service not received, or overcharging."
        ],
        "next_best_actions": [
            "Initiate the chargeback process if the dispute meets card network criteria.",
            "Temporarily block the disputed amount in the billing cycle during investigation.",
            "Coordinate with the merchant's acquiring bank for transaction details.",
            "Resolve and update the billing statement post investigation."
        ]
    },
    {
        "sub_issue": "Incorrect Interest Charged",
        "investigation_steps": [
            "Retrieve the interest calculation record from the billing system.",
            "Verify the interest rate applied against the rate in the card agreement.",
            "Confirm the statement closing date, outstanding balance, and payment history.",
            "Check if any prior payment was posted late, affecting the interest computation."
        ],
        "next_best_actions": [
            "Recalculate the interest correctly and credit the difference to the card account.",
            "If the rate was applied incorrectly, fix the rate in the billing system.",
            "Issue a revised statement with the corrected interest.",
            "Escalate to the billing/product team if the error is systemic."
        ]
    },
    {
        "sub_issue": "Late Fee Charged Incorrectly",
        "investigation_steps": [
            "Verify the payment due date and the actual payment posting date from CBS.",
            "Confirm if the late fee was charged on a day within the grace period.",
            "Check if the customer's payment was received on time but posted late due to a processing delay.",
            "Review if the customer has a waiver or fee reversal policy applicable."
        ],
        "next_best_actions": [
            "Reverse the late fee if the payment was confirmed received on time.",
            "If the late fee was due to a bank-side processing delay, waive the fee and fix the process.",
            "Issue a reversal credit and update the card statement.",
            "Log the reversal in the complaint system."
        ]
    },
    {
        "sub_issue": "Finance Charges Incorrect",
        "investigation_steps": [
            "Retrieve the finance charge calculation record from the billing system.",
            "Verify the rate, outstanding balance, and billing period used for computation.",
            "Confirm if the charge includes balance from the previous billing cycle incorrectly.",
            "Check if any part-payment or credit was not considered in the calculation."
        ],
        "next_best_actions": [
            "Recalculate finance charges accurately and credit the difference.",
            "Fix the billing system computation if an error is identified.",
            "Issue a corrected billing statement.",
            "Escalate to the billing team for systemic review if the error affects multiple accounts."
        ]
    },
    {
        "sub_issue": "GST Charged Incorrectly",
        "investigation_steps": [
            "Retrieve the billing statement and identify the GST line items.",
            "Verify the GST rate applied against the prevailing rate and the applicable fee category.",
            "Confirm whether GST was applied on exempt charges (if any).",
            "Cross-check the GST computation with the bank's tax calculation model."
        ],
        "next_best_actions": [
            "Correct the GST computation and credit the difference to the card account.",
            "Issue a revised statement and GST invoice.",
            "Escalate to the tax/billing team if incorrect GST computation is systemic.",
            "Update the billing system tax configuration if the rate is wrong."
        ]
    },
    {
        "sub_issue": "Annual Fee Charged Incorrectly",
        "investigation_steps": [
            "Retrieve the annual fee charge record from the card billing system.",
            "Verify if the customer's card variant is eligible for an annual fee waiver (based on spend threshold or offer).",
            "Confirm the applicable annual fee as per the card agreement and the fee charged.",
            "Check if there is a fee reversal commitment or promotional offer on the account."
        ],
        "next_best_actions": [
            "If the fee was charged incorrectly, initiate a fee reversal credit to the card account.",
            "If the waiver criteria were met, process the waiver and credit the fee.",
            "Issue a revised statement with the corrected fee.",
            "Escalate to the product/billing team if the incorrect fee is applied to multiple accounts."
        ]
    },
    {
        "sub_issue": "Annual Fee Reversal Not Processed",
        "investigation_steps": [
            "Confirm if the customer's annual fee reversal request was received and logged.",
            "Verify the eligibility for reversal (spend threshold met, promotional offer, or bank's waiver policy).",
            "Check the card billing system for the reversal credit posting.",
            "Identify the delay point — request received but not processed, or eligibility not verified."
        ],
        "next_best_actions": [
            "Process the annual fee reversal if eligibility is confirmed.",
            "If eligibility is in dispute, escalate to the product team for clarification.",
            "Credit the reversed amount to the card account and issue a revised statement.",
            "Update the complaint system with reversal confirmation."
        ]
    },
    {
        "sub_issue": "Overlimit Fee Dispute",
        "investigation_steps": [
            "Confirm the credit limit and the outstanding balance at the time the overlimit fee was charged.",
            "Verify if the customer had opted into overlimit facility and the applicable fee.",
            "Check if the overlimit was caused by a legitimate transaction or a fee/charge that pushed the balance over the limit.",
            "Review if the overlimit fee disclosure was provided at account opening or during the statement period."
        ],
        "next_best_actions": [
            "If the overlimit fee was charged in error or without consent, reverse it.",
            "If the fee is valid, provide the transaction details to the relevant team for customer communication.",
            "Review and update the overlimit fee disclosure if needed.",
            "Log the outcome in the complaint system."
        ]
    },
    {
        "sub_issue": "Cash Advance Fee Dispute",
        "investigation_steps": [
            "Retrieve the cash advance transaction and the associated fee from the billing system.",
            "Verify the cash advance fee rate per the card agreement.",
            "Confirm if the transaction was classified as a cash advance correctly.",
            "Check if there are any fee waiver policies applicable to the customer."
        ],
        "next_best_actions": [
            "If the fee was applied at an incorrect rate, correct and credit the difference.",
            "If the transaction was misclassified as cash advance, re-classify and reverse the fee.",
            "If the fee is valid, document and communicate the outcome to the relevant team.",
            "Update the card billing system if a rate error is found."
        ]
    },
    {
        "sub_issue": "Minimum Due Incorrectly Calculated",
        "investigation_steps": [
            "Retrieve the billing system's minimum due calculation for the disputed statement period.",
            "Verify the calculation formula (% of outstanding + EMI dues + overdue + charges) per the card agreement.",
            "Confirm the outstanding balance used for the calculation is accurate.",
            "Check if any EMI or standing instruction amounts were incorrectly included or excluded."
        ],
        "next_best_actions": [
            "Recalculate the correct minimum due and update the card account.",
            "Issue a revised statement if the minimum due was overstated.",
            "Fix the billing system calculation logic if a formula error is identified.",
            "Escalate to the billing team for systemic review."
        ]
    },
    {
        "sub_issue": "Outstanding Balance Incorrect",
        "investigation_steps": [
            "Retrieve the full transaction and payment history for the card from CBS.",
            "Verify the opening balance, all debits, credits, and fees for the disputed period.",
            "Identify any missing payments or duplicate charges causing the balance discrepancy.",
            "Cross-check the statement balance with the real-time card account ledger."
        ],
        "next_best_actions": [
            "Reconcile the card account and correct the outstanding balance.",
            "Reverse any duplicate or erroneous charges contributing to the incorrect balance.",
            "Issue a corrected statement with the accurate outstanding balance.",
            "Escalate to the billing team if the discrepancy is systemic."
        ]
    },
    {
        "sub_issue": "Credit Limit Not Updated",
        "investigation_steps": [
            "Verify if a credit limit change request was approved and logged in the card management system.",
            "Confirm if the update was pushed to the card processing platform and the card network.",
            "Check for any system sync delay between the CBS and the card management system.",
            "Identify the approval status and any pending steps in the limit update workflow."
        ],
        "next_best_actions": [
            "Manually trigger the credit limit update in the card management system if approved.",
            "Ensure the updated limit is synced with the card network for authorization.",
            "Confirm the new limit is reflected in online/mobile banking and card statements.",
            "Log the update in the complaint system."
        ]
    },
    {
        "sub_issue": "Incorrect Credit Limit Reduction",
        "investigation_steps": [
            "Identify who initiated the credit limit reduction — system, risk team, or a request.",
            "Verify if a notification was sent to the customer before the reduction per RBI guidelines.",
            "Confirm if the reduction was based on a valid risk assessment or credit policy.",
            "Check if the reduction was applied to the correct account and the correct amount."
        ],
        "next_best_actions": [
            "If the reduction was in error, restore the credit limit immediately.",
            "If the reduction was policy-driven, confirm the process was followed correctly.",
            "Ensure the customer notification process was completed.",
            "Document the investigation and outcome in the complaint system."
        ]
    },
    {
        "sub_issue": "Credit Limit Enhancement Pending",
        "investigation_steps": [
            "Retrieve the credit limit enhancement request from the card management or CRM system.",
            "Check the request date, current approval stage, and pending steps.",
            "Confirm if the required income, credit bureau, and risk assessments have been completed.",
            "Review the SLA for credit limit enhancement and check for delays."
        ],
        "next_best_actions": [
            "Escalate the pending request to the credit underwriting team for priority processing.",
            "Complete any pending assessments and push the decision.",
            "Communicate the expected decision date to the customer-facing team.",
            "Update the card management system once the limit is approved and applied."
        ]
    },
    {
        "sub_issue": "Temporary Credit Limit Not Applied",
        "investigation_steps": [
            "Confirm if the temporary credit limit increase request was approved and logged.",
            "Check the card management system to verify if the temporary limit was applied.",
            "Confirm the effective period for the temporary limit.",
            "Review for any system sync issue between the approval system and the card processing platform."
        ],
        "next_best_actions": [
            "Manually apply the temporary credit limit in the card management system.",
            "Sync the limit with the card network for authorization purposes.",
            "Confirm the limit is reflected and operational.",
            "Set an expiry task in the card management system for the temporary limit end date."
        ]
    },
    {
        "sub_issue": "Available Credit Not Updated",
        "investigation_steps": [
            "Review the card account ledger for all recent debits, credits, and payments.",
            "Confirm if a recent payment or credit was posted but not reflected in the available credit.",
            "Check for any authorization holds that are reducing the available credit.",
            "Verify the real-time available credit calculation in the card management system."
        ],
        "next_best_actions": [
            "Release any expired authorization holds that are artificially reducing available credit.",
            "If a payment was posted but not credited, trace and apply the credit.",
            "Refresh the available credit calculation in the card management system.",
            "Confirm the correct available credit is reflected to the customer."
        ]
    },
    {
        "sub_issue": "EMI Conversion Failed",
        "investigation_steps": [
            "Retrieve the EMI conversion request from the card management system.",
            "Check the eligibility of the transaction for EMI conversion (amount, merchant, card type).",
            "Verify if the conversion request was processed by the billing system.",
            "Identify the failure code or reason from the EMI conversion service."
        ],
        "next_best_actions": [
            "Retry the EMI conversion from the card management admin console.",
            "If the transaction is ineligible, advise the business team accordingly.",
            "If the conversion is a system error, escalate to the billing tech team.",
            "Confirm the EMI schedule is applied correctly after successful conversion."
        ]
    },
    {
        "sub_issue": "EMI Cancellation Failed",
        "investigation_steps": [
            "Check the EMI cancellation request log in the card management system.",
            "Confirm the current EMI status (active, pre-closed, cancellation pending).",
            "Identify the failure reason from the EMI management service.",
            "Check if any prepayment penalty or foreclosure fee applies."
        ],
        "next_best_actions": [
            "Retry the EMI cancellation from the admin console after resolving the root cause.",
            "If a penalty applies, confirm the amount and process accordingly.",
            "If system error, escalate to the billing tech team.",
            "Confirm EMI cancellation and update the card billing schedule."
        ]
    },
    {
        "sub_issue": "EMI Paid but Still Showing Due",
        "investigation_steps": [
            "Confirm the EMI payment posting date in CBS.",
            "Check the EMI management system to see if the payment was applied to the EMI schedule.",
            "Identify if there is a sync delay between the payment system and the EMI module.",
            "Verify the EMI due date and the payment date to confirm timely payment."
        ],
        "next_best_actions": [
            "Manually update the EMI payment in the EMI management module.",
            "Trigger a sync between CBS and the EMI billing system.",
            "Issue a revised EMI schedule reflecting the correct payment.",
            "Escalate to the billing tech team if the sync issue is systemic."
        ]
    },
    {
        "sub_issue": "EMI Schedule Incorrect",
        "investigation_steps": [
            "Retrieve the EMI schedule from the card billing system.",
            "Verify the principal amount, interest rate, tenure, and EMI installment amounts.",
            "Compare the computed EMI with the formula in the card agreement.",
            "Confirm if there are any prepayments or conversions that should have adjusted the schedule."
        ],
        "next_best_actions": [
            "Recalculate the correct EMI schedule and update the billing system.",
            "Issue a revised EMI schedule to the customer-facing team.",
            "Reverse any incorrect EMI charges and apply the correct amounts.",
            "Escalate to the billing team if the error is systemic across EMI accounts."
        ]
    },
    {
        "sub_issue": "Auto-Debit Failed",
        "investigation_steps": [
            "Retrieve the auto-debit instruction details from the NACH/SI management system.",
            "Confirm the customer's linked account had sufficient balance on the debit date.",
            "Check if the NACH mandate is active and correctly registered.",
            "Review the NPCI NACH response code for the failure reason."
        ],
        "next_best_actions": [
            "If balance was insufficient, log the failure and initiate the late payment process as per policy.",
            "If the mandate is inactive, re-register after customer authorization.",
            "If technical failure, retry the auto-debit in the next available window.",
            "Update the payment management system and notify the collections team if payment remains outstanding."
        ]
    },
    {
        "sub_issue": "Auto-Debit Registered Incorrectly",
        "investigation_steps": [
            "Retrieve the NACH/SI registration details from the mandate management system.",
            "Compare the registered amount, frequency, and account details with the customer's intended instruction.",
            "Identify when and by whom the incorrect registration was made.",
            "Check if any payments were executed under the incorrect mandate."
        ],
        "next_best_actions": [
            "Cancel the incorrectly registered mandate immediately.",
            "Re-register the mandate with correct parameters after customer authorization.",
            "If incorrect debits were made, initiate reversal for overpaid amounts.",
            "Update the mandate management system and document the correction."
        ]
    },
    {
        "sub_issue": "Standing Instruction Failed",
        "investigation_steps": [
            "Check the standing instruction execution log in CBS for the failure date and reason.",
            "Verify the instruction parameters (amount, date, beneficiary/payment head) are valid.",
            "Confirm the linked account had sufficient balance on the execution date.",
            "Check if any account restriction prevented the debit."
        ],
        "next_best_actions": [
            "If balance was insufficient, log the failure per bank policy.",
            "If account is restricted, investigate and lift restriction if valid.",
            "Reprocess the standing instruction if it was a one-time technical failure.",
            "Update the standing instruction record and confirm next execution."
        ]
    },
    {
        "sub_issue": "Statement Not Generated",
        "investigation_steps": [
            "Check the card billing system for the statement generation status for the billing period.",
            "Identify if the statement generation job failed or was skipped.",
            "Verify if there were any system issues during the billing run.",
            "Confirm if there is a zero-balance account exception causing statement skip."
        ],
        "next_best_actions": [
            "Trigger a manual statement generation for the affected billing period.",
            "Escalate to the billing tech team if the generation job is failing.",
            "Dispatch the generated statement via email and post.",
            "Confirm the statement is correctly generated and dispatched."
        ]
    },
    {
        "sub_issue": "Statement Not Received",
        "investigation_steps": [
            "Confirm the statement was generated and the dispatch method (email, post, e-statement).",
            "Verify the registered email address and mailing address in CBS.",
            "Check email delivery logs for bounce, spam filter, or delivery failure.",
            "For postal statements, check the dispatch date and courier tracking."
        ],
        "next_best_actions": [
            "Resend the statement to the correct registered email or address.",
            "If the email bounced, update the email ID after verification and resend.",
            "If postal statement is undelivered, arrange re-dispatch or provide a digital copy.",
            "Confirm receipt and update the complaint system."
        ]
    },
    {
        "sub_issue": "Incorrect Statement",
        "investigation_steps": [
            "Retrieve the card statement and cross-check each line item against CBS and card network records.",
            "Identify incorrect amounts, wrong merchants, missing transactions, or incorrect fees.",
            "Determine if the error is in the statement generation logic or the underlying transaction data.",
            "Confirm the billing period and all relevant inputs."
        ],
        "next_best_actions": [
            "Correct the statement data in the billing system.",
            "Issue a revised corrected statement.",
            "If unauthorized transactions are found, initiate chargeback.",
            "Escalate to the billing tech team if the error is systemic."
        ]
    },
    {
        "sub_issue": "Missing Transactions in Statement",
        "investigation_steps": [
            "Compare the card statement with the card transaction ledger in CBS.",
            "Identify the specific transactions missing from the statement.",
            "Check if the transactions were processed after the billing cycle cutoff.",
            "Confirm if the transactions were authorized but not settled before the statement date."
        ],
        "next_best_actions": [
            "If transactions are post-cutoff, they will appear in the next statement — confirm this with the operations team.",
            "If transactions should have appeared but are missing due to a system error, regenerate the statement.",
            "Issue a revised statement with all transactions included.",
            "Escalate to the billing tech team if transactions are incorrectly excluded."
        ]
    },
    {
        "sub_issue": "Duplicate Transactions in Statement",
        "investigation_steps": [
            "Retrieve the statement and identify the duplicate entries.",
            "Compare with CBS and card network records to confirm if the duplicates are real debits or billing errors.",
            "Check the statement generation logic for any duplication bugs.",
            "Confirm if the customer was actually charged twice."
        ],
        "next_best_actions": [
            "If the duplicates are real debits, initiate chargeback for the extra charge.",
            "If the duplicates are a statement rendering error, regenerate and issue a corrected statement.",
            "Escalate to the billing tech team to fix the duplication bug.",
            "Update the complaint system with the corrected statement details."
        ]
    },
    {
        "sub_issue": "Reward Points Not Credited",
        "investigation_steps": [
            "Retrieve the transaction eligible for reward points from the card transaction system.",
            "Confirm the reward point earning rate applicable to the transaction category and merchant.",
            "Check if the transaction was excluded from earning points (e.g., fuel, cash advance, EMI).",
            "Review the rewards management system for the point credit status."
        ],
        "next_best_actions": [
            "If points were not credited due to a system error, manually credit the correct points.",
            "If the transaction is ineligible, advise the customer-facing team with the reason.",
            "Escalate to the rewards management team if mass point credits are missing.",
            "Update the complaint system with the credit confirmation."
        ]
    },
    {
        "sub_issue": "Reward Points Expired Incorrectly",
        "investigation_steps": [
            "Retrieve the reward points balance and expiry history from the rewards management system.",
            "Confirm the expiry date and the basis for the expiry (inactivity, period-based, card closure).",
            "Verify if the card was active and eligible at the time of expiry.",
            "Check if any recent transaction should have reset the expiry clock."
        ],
        "next_best_actions": [
            "If points expired in error, restore the expired points in the rewards system.",
            "If the expiry was based on an incorrect trigger, fix the rewards expiry logic.",
            "Issue a revised rewards statement.",
            "Escalate to the rewards tech team if systemic errors caused incorrect expiry."
        ]
    },
    {
        "sub_issue": "Reward Points Redemption Failed",
        "investigation_steps": [
            "Retrieve the redemption request from the rewards management system.",
            "Confirm the available points balance and the redemption value requested.",
            "Check if the redemption channel (app, website, catalogue) was functional at the time.",
            "Review the error code from the rewards redemption service."
        ],
        "next_best_actions": [
            "Retry the redemption from the rewards admin console.",
            "If the redemption platform was down, escalate to the rewards tech team.",
            "If eligibility was the issue, clarify with the rewards team and communicate.",
            "Confirm successful redemption and update the complaint system."
        ]
    },
    {
        "sub_issue": "Cashback Not Credited",
        "investigation_steps": [
            "Retrieve the transaction for which cashback was expected from the card management system.",
            "Confirm the cashback eligibility criteria (merchant, amount, offer period).",
            "Check the rewards/cashback management system for the credit posting.",
            "Verify if the cashback credit cycle has been completed for the relevant period."
        ],
        "next_best_actions": [
            "If eligible and not credited, manually process the cashback credit.",
            "If the credit cycle is pending, monitor and confirm in the next cycle.",
            "Escalate to the cashback/rewards team if the credit is systematically missing.",
            "Confirm cashback credit and update the complaint system."
        ]
    },
    {
        "sub_issue": "Cashback Reversed Incorrectly",
        "investigation_steps": [
            "Retrieve the cashback reversal record from the rewards/cashback management system.",
            "Identify who initiated the reversal and the stated reason.",
            "Confirm if the transaction that triggered the cashback was returned or cancelled.",
            "Verify if the reversal policy was correctly applied."
        ],
        "next_best_actions": [
            "If the reversal was in error, reinstate the cashback credit.",
            "If the reversal was valid (transaction returned), confirm the process was correct.",
            "Issue a corrected rewards statement.",
            "Escalate to the cashback team for process review if reversals are erroneous."
        ]
    },
    {
        "sub_issue": "Offer Benefit Not Applied",
        "investigation_steps": [
            "Retrieve the offer terms and eligibility criteria for the disputed benefit.",
            "Confirm the transaction met all offer criteria (merchant, amount, date, card type).",
            "Check the offer management system for the benefit application status.",
            "Review if the offer was correctly registered on the card/account."
        ],
        "next_best_actions": [
            "If eligible and not applied, manually apply the benefit via the offer management system.",
            "If there is an offer registration issue, correct and re-apply.",
            "Escalate to the offers/product team if systemic non-application is found.",
            "Confirm benefit application and update the complaint system."
        ]
    },
    {
        "sub_issue": "Voucher Redemption Failed",
        "investigation_steps": [
            "Retrieve the voucher code and the redemption attempt logs from the rewards system.",
            "Confirm the voucher is valid, not expired, and applicable to the attempted redemption.",
            "Check if the voucher redemption platform was operational at the time.",
            "Identify the failure code from the redemption API."
        ],
        "next_best_actions": [
            "If the platform was down, escalate to the rewards tech team for fix.",
            "Retry the voucher redemption after root cause resolution.",
            "If the voucher is expired due to a bank error, issue a replacement voucher.",
            "Confirm successful redemption and update the complaint system."
        ]
    },
    {
        "sub_issue": "Credit Card Closure Delay",
        "investigation_steps": [
            "Retrieve the credit card closure request from the CRM and confirm the date received.",
            "Check the current status of the closure — pending clearance of dues, pending confirmation, or stuck in processing.",
            "Confirm if all dues are cleared, mandates cancelled, and add-on cards deactivated.",
            "Review the SLA for card closure and identify the delay point."
        ],
        "next_best_actions": [
            "Escalate the closure request to the card operations team for priority processing.",
            "Ensure all prerequisites (dues cleared, mandates cancelled) are completed.",
            "Process the card closure once all conditions are met.",
            "Issue a No Dues Certificate (NDC) after closure and update the complaint system."
        ]
    },
    {
        "sub_issue": "Credit Card Closure Not Processed",
        "investigation_steps": [
            "Confirm the closure request was received and logged in the CRM.",
            "Check if the closure was rejected or stuck in a pending state.",
            "Identify the reason for non-processing — outstanding dues, dispute pending, or system error.",
            "Confirm if the customer was informed of any pending prerequisites."
        ],
        "next_best_actions": [
            "Clear all prerequisites and process the card closure immediately.",
            "If a system error, escalate to the card platform tech team.",
            "Issue a No Dues Certificate after closure.",
            "Update the complaint system with closure confirmation and NDC details."
        ]
    },
    {
        "sub_issue": "Closure Request Rejected",
        "investigation_steps": [
            "Retrieve the rejection reason from the card management system.",
            "Confirm if the rejection was due to outstanding dues, pending disputes, active mandates, or policy reasons.",
            "Verify if the rejection reason is valid and documented per bank policy.",
            "Check if the customer was notified of the rejection and the reason."
        ],
        "next_best_actions": [
            "If the rejection was in error, process the closure immediately.",
            "If rejection is valid, communicate the specific pre-conditions for closure to the relevant team.",
            "Once prerequisites are met, re-process the closure.",
            "Update the complaint system with the outcome."
        ]
    },
    {
        "sub_issue": "Closed Card Still Active",
        "investigation_steps": [
            "Verify the card closure completion status in the card management system.",
            "Confirm if the card was deactivated in the card network's system.",
            "Check if any transactions occurred after the closure date.",
            "Identify if the card was closed in CBS but not in the card network."
        ],
        "next_best_actions": [
            "Immediately deactivate the card in the card network's system.",
            "Review and reverse any transactions made post-closure if unauthorized.",
            "Escalate to the card ops and tech team to fix the closure process.",
            "Audit other recently closed cards to identify systemic gaps."
        ]
    },
    {
        "sub_issue": "No Dues Certificate Not Issued",
        "investigation_steps": [
            "Confirm the card closure status in the card management system.",
            "Verify that all dues, fees, and outstanding amounts have been cleared.",
            "Check if the NDC issuance process was triggered after closure.",
            "Identify the reason for non-issuance — system gap, pending dues, or process failure."
        ],
        "next_best_actions": [
            "Issue the No Dues Certificate from the card management system after confirming zero balance.",
            "If dues are pending, clear them first and then issue the NDC.",
            "Dispatch the NDC via email/courier as per the customer's preference.",
            "Update the complaint system and CRM with the NDC details."
        ]
    },
    {
        "sub_issue": "Card Upgrade Not Processed",
        "investigation_steps": [
            "Retrieve the card upgrade request from the CRM and confirm the request date.",
            "Check if the customer meets the eligibility criteria for the target card variant.",
            "Confirm the current status in the card upgrade workflow.",
            "Identify any pending approvals or documentation holding up the upgrade."
        ],
        "next_best_actions": [
            "Process the upgrade request after eligibility confirmation.",
            "Coordinate the upgrade with the card production team for issuance of the new variant.",
            "Deactivate the old card and activate the new upgraded card.",
            "Communicate the upgrade timeline to the customer-facing team."
        ]
    },
    {
        "sub_issue": "Card Downgrade Without Consent",
        "investigation_steps": [
            "Identify who initiated the card downgrade and the reason (risk review, credit review, or system trigger).",
            "Confirm if the customer was notified before the downgrade per RBI guidelines.",
            "Verify if the downgrade was policy-compliant and documented.",
            "Check if the customer's benefits, limits, and features changed due to the downgrade."
        ],
        "next_best_actions": [
            "If the downgrade was in error, reverse it and restore the original card variant.",
            "If the downgrade was policy-driven but without notice, issue the required notification.",
            "Escalate to compliance if RBI customer notification norms were violated.",
            "Document the investigation and escalation in the complaint and compliance systems."
        ]
    },
    {
        "sub_issue": "Card Variant Change Pending",
        "investigation_steps": [
            "Retrieve the card variant change request and check its status in the card management system.",
            "Identify the pending stage — eligibility verification, approval, or card production.",
            "Review the SLA for variant changes and check for delays.",
            "Confirm if all required documents and approvals are in place."
        ],
        "next_best_actions": [
            "Escalate the pending request to the card operations team for priority processing.",
            "Complete any pending steps and push the request to the next stage.",
            "Communicate the expected completion date to the customer-facing team.",
            "Confirm variant change completion in the card management system."
        ]
    },
    {
        "sub_issue": "Add-on Card Not Received",
        "investigation_steps": [
            "Confirm the add-on card was issued and dispatched.",
            "Retrieve the dispatch date and courier tracking details.",
            "Verify the delivery address used for the add-on card.",
            "Check courier delivery status including failed attempts or returns."
        ],
        "next_best_actions": [
            "If undelivered, coordinate with the courier for redelivery or branch pickup.",
            "If the address was incorrect, update CBS and re-dispatch.",
            "If the card is lost in transit, hotlist and reorder.",
            "Confirm delivery and update the complaint system."
        ]
    },
    {
        "sub_issue": "Add-on Card Activation Failed",
        "investigation_steps": [
            "Check the add-on card activation service logs for the failure code.",
            "Verify the add-on card number, expiry, and CVV entered during activation.",
            "Confirm the add-on card is in pre-activation state in the card management system.",
            "Identify the failure channel (IVR, app, net banking)."
        ],
        "next_best_actions": [
            "Manually activate the add-on card from the card management admin console.",
            "If service error, escalate to the card tech team.",
            "Confirm activation and inform the customer-facing team.",
            "Log activation confirmation in the complaint system."
        ]
    },
    {
        "sub_issue": "Supplementary Card Issue",
        "investigation_steps": [
            "Review the supplementary card application and identify the nature of the issue (not received, activation failed, limit dispute).",
            "Confirm the supplementary card's issuance status in the card management system.",
            "Check the delivery status if the card was dispatched.",
            "Verify the supplementary cardholder's KYC and eligibility."
        ],
        "next_best_actions": [
            "Resolve the identified issue — reissue, reactivate, or re-dispatch as applicable.",
            "Confirm the supplementary card is operational.",
            "Update the card management system and the complaint system.",
            "Coordinate with the primary cardholder account team as needed."
        ]
    },
    {
        "sub_issue": "Virtual Card Creation Failed",
        "investigation_steps": [
            "Check the virtual card creation service logs for the failure code.",
            "Verify the customer's eligibility for virtual card creation (active account, no restrictions).",
            "Confirm if the virtual card platform/API is operational.",
            "Identify if the failure is at the bank's end or the card network's tokenization service."
        ],
        "next_best_actions": [
            "Retry virtual card creation from the admin console after root cause resolution.",
            "Escalate to the card tech team if the virtual card service is down.",
            "Coordinate with the card network's tokenization team if the failure is network-side.",
            "Confirm virtual card creation and update the complaint system."
        ]
    },
    {
        "sub_issue": "Virtual Card Not Working",
        "investigation_steps": [
            "Confirm the virtual card's status (active, expired, blocked) in the card management system.",
            "Check the virtual card number, CVV, and expiry being used for the transaction.",
            "Verify if the merchant accepts virtual cards.",
            "Review the transaction failure code from the authorization logs."
        ],
        "next_best_actions": [
            "If the virtual card is expired or blocked, reissue a new virtual card.",
            "If the merchant does not accept virtual cards, note this and advise the relevant team.",
            "If a system error, escalate to the card tech team.",
            "Confirm the virtual card is working post-fix."
        ]
    },
    {
        "sub_issue": "Virtual Card Expired Incorrectly",
        "investigation_steps": [
            "Retrieve the virtual card details from the card management system and confirm the set expiry date.",
            "Compare the expiry date with the expected validity period at issuance.",
            "Identify if the expiry was triggered by an incorrect system rule or manual action.",
            "Check if the early expiry caused any transaction failures."
        ],
        "next_best_actions": [
            "Extend or reissue the virtual card with the correct expiry date.",
            "Reverse any failed transactions caused by the incorrect expiry and reprocess.",
            "Fix the expiry rule in the virtual card management system.",
            "Update the complaint system with the resolution details."
        ]
    },
    {
        "sub_issue": "Registered Mobile Number Not Updated",
        "investigation_steps": [
            "Confirm if a mobile number update request was received and logged in the CRM.",
            "Check the CBS and card management system for the current registered mobile number.",
            "Identify if the update is pending due to KYC/OTP verification or a system error.",
            "Confirm if the number update is reflected in all associated systems."
        ],
        "next_best_actions": [
            "Process the mobile number update in CBS after identity verification.",
            "Sync the updated number across the card management system and communication platforms.",
            "Confirm OTP and communication delivery to the new number.",
            "Update the complaint system with the change confirmation."
        ]
    },
    {
        "sub_issue": "Email ID Not Updated",
        "investigation_steps": [
            "Confirm the email ID update request in the CRM.",
            "Check CBS and the card management system for the current email ID.",
            "Identify if the update is pending due to email verification or a system error.",
            "Confirm if statements and communications are being sent to the old email."
        ],
        "next_best_actions": [
            "Process the email ID update in CBS after verification.",
            "Sync the new email ID across all card and communication systems.",
            "Resend any missed statements or communications to the new email.",
            "Update the complaint system with the change confirmation."
        ]
    },
    {
        "sub_issue": "Address Update Pending",
        "investigation_steps": [
            "Confirm the address update request in the CRM and the submitted proof.",
            "Check the CBS and card management system for the current address.",
            "Identify if the update is pending due to KYC document verification or a system delay.",
            "Confirm if card dispatches or statements are being sent to the old address."
        ],
        "next_best_actions": [
            "Process the address update in CBS after verifying the address proof.",
            "Sync the updated address across all relevant systems.",
            "Re-dispatch any pending cards or statements to the new address.",
            "Update the complaint system with the change confirmation."
        ]
    },
    {
        "sub_issue": "Name Correction Pending",
        "investigation_steps": [
            "Confirm the name correction request and supporting documents submitted.",
            "Check the CBS and card management system for the current registered name.",
            "Identify the pending step — document verification, legal name match, or system update.",
            "Confirm if the name on the card matches the registered name."
        ],
        "next_best_actions": [
            "Process the name correction in CBS after verifying the legal name proof.",
            "Reissue the card with the corrected name if the physical card has an error.",
            "Sync the corrected name across all card and communication systems.",
            "Update the complaint system with the correction confirmation."
        ]
    },
    {
        "sub_issue": "KYC Pending for Credit Card",
        "investigation_steps": [
            "Identify the specific KYC documents or steps pending for the credit card account.",
            "Check if the customer submitted documents and their current verification status.",
            "Confirm if the pending KYC is affecting card issuance or transaction capability.",
            "Review the KYC SLA and identify delay reasons."
        ],
        "next_best_actions": [
            "Expedite the KYC verification with the compliance/KYC team.",
            "If documents are missing, log and notify the customer-facing team.",
            "Once KYC is complete, update the card management system and restore full functionality.",
            "Update the complaint system with KYC completion status."
        ]
    },
    {
        "sub_issue": "Insurance Added Without Consent",
        "investigation_steps": [
            "Retrieve the insurance activation record from the card management or insurance platform.",
            "Identify who authorized the insurance addition and confirm the consent documentation.",
            "Check if the insurance premium was charged to the card account.",
            "Review the insurance sales and onboarding process for compliance with RBI guidelines."
        ],
        "next_best_actions": [
            "Cancel the insurance policy immediately if added without customer consent.",
            "Reverse all insurance premium charges from the card account.",
            "Escalate to the compliance team as a mis-selling or forced selling violation.",
            "File an internal report and review the sales process for systemic issues."
        ]
    },
    {
        "sub_issue": "Credit Shield Cancellation Pending",
        "investigation_steps": [
            "Retrieve the credit shield cancellation request from the CRM.",
            "Confirm the cancellation request date and current processing status.",
            "Check if premiums were charged after the cancellation request.",
            "Identify the delay point — insurance platform, internal processing, or documentation."
        ],
        "next_best_actions": [
            "Process the credit shield cancellation immediately.",
            "Reverse any premiums charged after the cancellation request date.",
            "Coordinate with the insurance team to confirm policy termination.",
            "Issue a cancellation confirmation and update the complaint system."
        ]
    },
    {
        "sub_issue": "Credit Bureau Reporting Incorrect",
        "investigation_steps": [
            "Retrieve the credit bureau report for the customer and identify the incorrect data fields.",
            "Compare the bureau data with the bank's internal records (outstanding, payment history, credit limit).",
            "Identify when the incorrect data was reported and the cause.",
            "Check if the incorrect reporting has affected the customer's credit score."
        ],
        "next_best_actions": [
            "Submit a correction request to the credit bureau (CIBIL/Experian/Equifax/CRIF) with accurate data.",
            "Update the internal reporting module to correct the error for future submissions.",
            "Monitor the bureau to confirm the correction is applied in the next reporting cycle.",
            "Escalate to the credit bureau reporting team if the correction is rejected."
        ]
    },
    {
        "sub_issue": "Card Delivery to Wrong Address",
        "investigation_steps": [
            "Retrieve the dispatch record and confirm the delivery address used.",
            "Compare the dispatch address with the registered address in CBS.",
            "Check if the customer had recently updated their address and the update was not synced.",
            "Confirm with the courier if the card was delivered to the wrong address."
        ],
        "next_best_actions": [
            "Hotlist the card dispatched to the wrong address immediately to prevent misuse.",
            "Reorder and dispatch a new card to the correct address.",
            "Investigate the address data sync issue and fix it.",
            "Update the complaint system and monitor for delivery confirmation of the reordered card."
        ]
    },
    {
        "sub_issue": "Card Application Rejected Without Reason",
        "investigation_steps": [
            "Retrieve the credit card application and the automated/manual decision from the underwriting system.",
            "Confirm the rejection reason — credit score, income, policy, or KYC.",
            "Verify if the rejection reason was communicated to the customer per RBI norms.",
            "Check if the rejection was based on accurate data (e.g., correct bureau report)."
        ],
        "next_best_actions": [
            "Communicate the rejection reason to the applicant via appropriate channel as required by RBI.",
            "If the rejection was based on incorrect data, review the application and correct the data.",
            "Escalate to compliance if rejection reasons are systematically not being communicated.",
            "Document the case and outcome in the complaint and underwriting systems."
        ]
    },
    {
        "sub_issue": "Card Issuance Delay",
        "investigation_steps": [
            "Retrieve the credit card application and approval status from the card management system.",
            "Confirm if the card was approved and sent for production.",
            "Track the card production and dispatch status with the card production vendor.",
            "Identify the delay point — underwriting, production, or dispatch."
        ],
        "next_best_actions": [
            "Coordinate with the card production team to expedite production and dispatch.",
            "If underwriting is pending, escalate to the credit team for priority review.",
            "Provide the customer-facing team with the expected delivery date.",
            "Confirm dispatch and track delivery in the complaint system."
        ]
    }
],
[
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Lost",
    "investigation_steps": [
      "Verify card status in CBS and card management system (CMS)",
      "Check last transaction timestamp and channel used",
      "Review hotlisting/blocking history in CMS",
      "Verify customer-reported loss date against transaction logs",
      "Check if any transactions occurred post reported loss date",
      "Review switch logs for any post-loss usage attempts"
    ],
    "next_best_actions": [
      "Hotlist card immediately in CMS if not already blocked",
      "Initiate chargeback for any unauthorized post-loss transactions",
      "Trigger replacement card issuance workflow",
      "Update card status in CBS to Lost",
      "Flag account for enhanced monitoring"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Stolen",
    "investigation_steps": [
      "Verify card status in CBS and CMS",
      "Check last transaction timestamp and channel used",
      "Review hotlisting/blocking history in CMS",
      "Verify customer-reported theft date against transaction logs",
      "Check if any transactions occurred post reported theft date",
      "Review switch logs for any post-theft usage attempts"
    ],
    "next_best_actions": [
      "Hotlist card immediately in CMS if not already blocked",
      "Initiate chargeback for any unauthorized post-theft transactions",
      "Trigger replacement card issuance workflow",
      "Update card status in CBS to Stolen",
      "Flag account for enhanced monitoring",
      "Coordinate with fraud management team for investigation"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Unauthorized Transaction",
    "investigation_steps": [
      "Retrieve transaction details from CBS and switch logs",
      "Verify transaction authentication method (PIN/OTP/Contactless)",
      "Check if card was physically present or card-not-present transaction",
      "Review OTP delivery logs and SMS gateway records",
      "Verify 3D Secure authentication logs for online transactions",
      "Check device fingerprint and IP address for online transactions",
      "Review merchant MCC and transaction origin details",
      "Verify card status at time of transaction in CMS"
    ],
    "next_best_actions": [
      "Hotlist card immediately if not already blocked",
      "Initiate chargeback with acquiring bank via NPCI/Visa/Mastercard",
      "Raise dispute with payment network",
      "Initiate provisional credit to customer account pending dispute resolution",
      "Escalate to fraud management team",
      "Flag account for enhanced monitoring"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Unauthorized Debit",
    "investigation_steps": [
      "Retrieve debit transaction details from CBS",
      "Verify transaction origin: POS, ATM, online, or standing instruction",
      "Check if debit corresponds to any registered standing instruction or auto-debit mandate",
      "Review switch logs for transaction authentication trail",
      "Verify OTP and 3D Secure logs if online transaction",
      "Check merchant details and acquiring bank information",
      "Confirm card was not shared or compromised based on recent transaction patterns"
    ],
    "next_best_actions": [
      "Hotlist card if compromise suspected",
      "Initiate chargeback with acquiring bank",
      "Reverse unauthorized debit if internal processing error confirmed",
      "Cancel any unauthorized standing instructions or mandates",
      "Escalate to fraud management team",
      "Initiate provisional credit pending dispute resolution"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Fraudulent Transaction",
    "investigation_steps": [
      "Retrieve transaction details from CBS and switch logs",
      "Verify authentication method used (PIN/OTP/Biometric)",
      "Check velocity of transactions for fraud pattern identification",
      "Review merchant MCC, terminal ID, and acquiring bank details",
      "Check device fingerprint, IP address, and geolocation for online transactions",
      "Review fraud scoring system logs and alerts triggered",
      "Verify card status and recent block/unblock history in CMS",
      "Cross-reference with known fraud patterns in fraud management system"
    ],
    "next_best_actions": [
      "Hotlist card immediately",
      "Initiate chargeback with payment network",
      "Escalate to fraud management team for deeper investigation",
      "Initiate provisional credit to customer account",
      "Report fraud case to NPCI fraud reporting portal if applicable",
      "Flag account for enhanced monitoring"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Fraudulent International Transaction",
    "investigation_steps": [
      "Retrieve international transaction details from CBS and switch logs",
      "Verify if international usage was enabled on card in CMS",
      "Check authentication method used for international transaction",
      "Review geolocation of transaction against customer's known profile",
      "Check 3D Secure authentication logs for card-not-present transactions",
      "Verify merchant country, MCC, and acquiring bank details",
      "Review fraud scoring system logs for international fraud flags",
      "Check if customer was traveling internationally at time of transaction"
    ],
    "next_best_actions": [
      "Hotlist card immediately",
      "Initiate chargeback with international payment network (Visa/Mastercard)",
      "Escalate to fraud management team",
      "Disable international usage on replacement card until customer request",
      "Initiate provisional credit to customer account",
      "Report to NPCI and relevant payment network fraud desk"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Compromised",
    "investigation_steps": [
      "Verify card status in CBS and CMS",
      "Review recent transaction history for suspicious patterns",
      "Check if card data was used across multiple unauthorized channels",
      "Review fraud alert logs and fraud scoring system",
      "Check if card number appears in any known data breach alerts",
      "Verify POS terminals used recently for skimming risk assessment",
      "Review switch logs for any unusual transaction patterns"
    ],
    "next_best_actions": [
      "Hotlist card immediately in CMS",
      "Initiate chargeback for all identified unauthorized transactions",
      "Trigger replacement card issuance workflow",
      "Escalate to fraud management team",
      "Report compromise to NPCI and payment network if systemic breach suspected",
      "Flag account for enhanced monitoring"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Cloned",
    "investigation_steps": [
      "Retrieve transaction logs from CBS and switch for suspected cloned card usage",
      "Identify transactions where physical card was used simultaneously at different locations",
      "Review POS terminal IDs where card was recently used for skimming risk",
      "Check fraud management system for cloning pattern alerts",
      "Verify chip vs magnetic stripe transaction logs to identify stripe-read transactions",
      "Coordinate with acquiring banks of suspected terminals"
    ],
    "next_best_actions": [
      "Hotlist card immediately in CMS",
      "Initiate chargeback for all cloned card transactions",
      "Trigger replacement card issuance (EMV chip card)",
      "Escalate to fraud management and card operations team",
      "Report suspected skimming terminal to NPCI",
      "Flag account for enhanced monitoring"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Suspicious Transaction",
    "investigation_steps": [
      "Retrieve transaction details from CBS and switch logs",
      "Review fraud scoring system for risk score on flagged transaction",
      "Verify authentication method used",
      "Check transaction geolocation, device, and IP address",
      "Review recent transaction velocity and pattern",
      "Verify merchant MCC and acquiring bank details",
      "Check if customer was notified via SMS/email alert"
    ],
    "next_best_actions": [
      "Temporarily block card pending customer confirmation",
      "Initiate chargeback if transaction confirmed unauthorized",
      "Release block if transaction confirmed legitimate by customer",
      "Escalate to fraud management team if fraud confirmed",
      "Update fraud scoring model with flagged transaction data"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Blocked Without Notice",
    "investigation_steps": [
      "Verify card block status and reason code in CMS",
      "Check CBS for any system-triggered block events (fraud, regulatory, dormancy)",
      "Review fraud management system for auto-block triggers",
      "Verify if RBI/NPCI compliance trigger caused block",
      "Check SMS/email notification delivery logs for block alert",
      "Review customer communication logs for prior intimation"
    ],
    "next_best_actions": [
      "Validate legitimacy of block reason",
      "Unblock card in CMS if block was erroneous",
      "Trigger SMS/email notification to customer with block reason",
      "Escalate to compliance team if regulatory block",
      "Update notification workflow to ensure future alerts are sent"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Block Request Not Processed",
    "investigation_steps": [
      "Verify card block request receipt in CRM/complaint management system",
      "Check CMS for current card status",
      "Review IVR, mobile banking, and branch logs for block request timestamp",
      "Verify if technical failure caused request drop",
      "Check switch logs for any transactions post block request"
    ],
    "next_best_actions": [
      "Block card immediately in CMS",
      "Initiate chargeback for any transactions occurring after block request timestamp",
      "Escalate to CMS/technical team to investigate request processing failure",
      "Update CRM with corrective action taken",
      "Review and fix block request processing workflow"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Unblocking Delay",
    "investigation_steps": [
      "Verify card block and unblock request logs in CMS and CRM",
      "Check reason for block and whether unblock criteria have been met",
      "Review workflow queue for pending unblock requests",
      "Check if compliance or fraud hold is preventing unblock",
      "Verify CBS account status linked to card"
    ],
    "next_best_actions": [
      "Unblock card in CMS if all criteria are satisfied",
      "Escalate to compliance or fraud team if hold is active",
      "Update CRM with resolution status",
      "Notify customer via SMS/email upon unblock",
      "Review unblock workflow SLA and fix bottleneck"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Hotlisting Request Failed",
    "investigation_steps": [
      "Verify hotlisting request in CMS and CRM",
      "Check CMS transaction logs for request failure error codes",
      "Review system/API logs between CRM and CMS for hotlist request failure",
      "Verify if card was already hotlisted or in another non-active status",
      "Check switch logs for any transactions post hotlisting request"
    ],
    "next_best_actions": [
      "Manually hotlist card in CMS immediately",
      "Initiate chargeback for any transactions post hotlist request timestamp",
      "Escalate technical failure to CMS/IT team for root cause analysis",
      "Update CRM with manual hotlisting action taken",
      "Monitor card for further unauthorized usage"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Activation Failed",
    "investigation_steps": [
      "Verify card issuance and activation status in CMS",
      "Check activation attempt logs (IVR, mobile banking, ATM)",
      "Verify card number, CVV, and expiry in CMS against physical card details",
      "Check if account linked to card is active in CBS",
      "Review error codes generated during activation attempt",
      "Verify KYC status of account holder"
    ],
    "next_best_actions": [
      "Retry activation in CMS if technical error identified",
      "Re-issue card if card data mismatch found",
      "Escalate to card operations team for manual activation",
      "Verify and resolve linked account issues in CBS",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Activation Pending",
    "investigation_steps": [
      "Verify card issuance and activation status in CMS",
      "Check activation request logs and pending queue",
      "Verify if card was dispatched and delivered to customer",
      "Review activation channel logs (IVR, mobile banking, ATM)",
      "Check for system queue backlog or processing delay in CMS"
    ],
    "next_best_actions": [
      "Force-activate card in CMS if eligible and all checks are passed",
      "Escalate to card operations team for manual processing",
      "Notify customer via SMS/email on activation status",
      "Update CRM with corrective action taken",
      "Monitor activation queue for systemic delays"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Replacement Card Not Received",
    "investigation_steps": [
      "Verify replacement card request in CMS and CRM",
      "Check card dispatch status and courier tracking number",
      "Verify delivery address used for dispatch against CBS records",
      "Review courier partner delivery logs",
      "Check if replacement card was returned undelivered"
    ],
    "next_best_actions": [
      "Initiate re-dispatch of replacement card to verified address",
      "Update delivery address in CBS if incorrect",
      "Coordinate with courier partner for delivery status",
      "Hotlist original replacement card if undelivered and at risk",
      "Update CRM with re-dispatch details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Replacement Card Delay",
    "investigation_steps": [
      "Verify replacement card request date in CMS and CRM",
      "Check card production and dispatch status in CMS",
      "Review courier partner tracking for dispatch and delivery status",
      "Identify stage of delay: production, dispatch, or delivery",
      "Verify delivery address in CBS"
    ],
    "next_best_actions": [
      "Escalate to card production/dispatch team to expedite",
      "Coordinate with courier partner to prioritize delivery",
      "Issue temporary virtual debit card if applicable",
      "Update CRM with expedited action details",
      "Notify customer via SMS/email with updated delivery timeline"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Renewal Card Not Received",
    "investigation_steps": [
      "Verify card renewal processing in CMS",
      "Check dispatch status and courier tracking for renewal card",
      "Verify delivery address used for dispatch against CBS records",
      "Review if renewal card was returned undelivered",
      "Check if old card was hotlisted post renewal"
    ],
    "next_best_actions": [
      "Initiate re-dispatch of renewal card to verified address",
      "Update delivery address in CBS if incorrect",
      "Coordinate with courier partner for delivery status",
      "Hotlist undelivered renewal card if at risk",
      "Update CRM with re-dispatch details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Renewal Delay",
    "investigation_steps": [
      "Verify card expiry date and renewal trigger in CMS",
      "Check card production queue for renewal card",
      "Review dispatch and courier status for renewal card",
      "Identify stage of delay: production, dispatch, or delivery",
      "Verify delivery address in CBS"
    ],
    "next_best_actions": [
      "Escalate to card production team to expedite renewal",
      "Coordinate with courier partner to prioritize delivery",
      "Issue temporary virtual debit card if applicable",
      "Update CRM with expedited action details",
      "Notify customer via SMS/email with updated delivery timeline"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Expired Incorrectly",
    "investigation_steps": [
      "Verify card expiry date in CMS against physical card details",
      "Check CBS for correct expiry date mapping",
      "Review if premature expiry was triggered by system error in CMS",
      "Verify if renewal card was issued prematurely causing old card expiry",
      "Check switch logs to confirm card rejection due to expiry"
    ],
    "next_best_actions": [
      "Correct card expiry date in CMS if data error identified",
      "Re-issue card with correct expiry if correction not possible",
      "Escalate to card operations team for CMS data correction",
      "Update CBS records to reflect corrected card details",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card PIN Generation Failed",
    "investigation_steps": [
      "Verify PIN generation request logs in CMS",
      "Check error codes generated during PIN generation attempt",
      "Verify channel used for PIN generation (IVR, mobile banking, ATM)",
      "Check if card is in active status in CMS",
      "Review HSM (Hardware Security Module) logs for PIN generation failures",
      "Verify linked mobile number for OTP-based PIN generation"
    ],
    "next_best_actions": [
      "Retry PIN generation process in CMS",
      "Escalate to card operations or IT team if HSM issue identified",
      "Trigger fresh PIN mailer if green PIN generation fails",
      "Update CRM with corrective action taken",
      "Verify and update registered mobile number if OTP delivery failed"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card PIN Reset Failed",
    "investigation_steps": [
      "Verify PIN reset request logs in CMS",
      "Check error codes generated during PIN reset attempt",
      "Verify channel used for PIN reset (IVR, mobile banking, ATM)",
      "Check if card is in active status in CMS",
      "Review HSM logs for PIN reset failures",
      "Verify registered mobile number for OTP delivery"
    ],
    "next_best_actions": [
      "Retry PIN reset in CMS",
      "Escalate to card operations or IT team if HSM failure confirmed",
      "Trigger fresh PIN mailer if reset cannot be completed electronically",
      "Update registered mobile number if OTP delivery was the failure cause",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Forgot Debit Card PIN",
    "investigation_steps": [
      "Verify card status in CMS (active/blocked)",
      "Check if PIN was previously generated and when",
      "Verify customer identity and account ownership",
      "Review PIN generation channel availability (IVR, mobile banking, ATM)"
    ],
    "next_best_actions": [
      "Initiate PIN generation via IVR, mobile banking, or ATM green PIN process",
      "Trigger PIN mailer if electronic generation is not available",
      "Update CRM with PIN reset action initiated",
      "Verify registered mobile number for OTP-based PIN reset"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "PIN Not Received",
    "investigation_steps": [
      "Verify PIN mailer dispatch status in CMS",
      "Check courier tracking for PIN mailer delivery",
      "Verify dispatch address against CBS records",
      "Check if PIN mailer was returned undelivered",
      "Verify if green PIN (electronic PIN) was offered but not used"
    ],
    "next_best_actions": [
      "Initiate green PIN generation via IVR or mobile banking",
      "Re-dispatch PIN mailer to verified address if electronic option unavailable",
      "Update delivery address in CBS if incorrect",
      "Update CRM with corrective action taken",
      "Coordinate with courier partner if mailer is in transit"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Incorrect PIN Accepted",
    "investigation_steps": [
      "Retrieve transaction logs from switch for the specific transaction",
      "Verify PIN validation logs in HSM and switch",
      "Check if card is chip-based or magnetic stripe and which was used",
      "Review terminal logs from the acquiring bank's POS/ATM",
      "Check for any system anomaly in PIN validation logic",
      "Verify if card was operating in fallback mode"
    ],
    "next_best_actions": [
      "Escalate to card operations and IT security team immediately",
      "Initiate forensic review of HSM and switch PIN validation logs",
      "Hotlist card if security compromise suspected",
      "Report to NPCI and payment network if systemic issue identified",
      "Initiate internal security audit of PIN validation process"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "ATM PIN Change Failed",
    "investigation_steps": [
      "Retrieve ATM transaction logs for PIN change attempt",
      "Check ATM switch logs for error codes during PIN change",
      "Verify HSM logs for PIN change processing failure",
      "Check if ATM was in online or offline mode during attempt",
      "Verify card status in CMS at time of PIN change attempt"
    ],
    "next_best_actions": [
      "Retry PIN change via alternative channel (IVR, mobile banking)",
      "Escalate to ATM operations team if ATM-specific issue identified",
      "Escalate to HSM/IT team if PIN processing failure identified",
      "Update CRM with corrective action taken",
      "Trigger fresh PIN mailer if all electronic options fail"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Swipe Failed",
    "investigation_steps": [
      "Retrieve POS transaction logs from switch",
      "Check error codes returned during swipe failure",
      "Verify card magnetic stripe status in CMS",
      "Check if merchant terminal was online and functional",
      "Verify if card was expired or blocked at time of swipe",
      "Review acquiring bank terminal logs"
    ],
    "next_best_actions": [
      "Verify card active status and reissue if magnetic stripe damaged",
      "Advise POS operator to retry or use alternate terminal",
      "Escalate to acquiring bank if terminal issue identified",
      "Initiate card replacement if physical card damage confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "POS Transaction Failed",
    "investigation_steps": [
      "Retrieve POS transaction logs from switch",
      "Check error codes returned during POS failure",
      "Verify card status in CMS at time of transaction",
      "Verify account balance and transaction limits in CBS",
      "Review acquiring bank terminal logs",
      "Check if amount was debited despite transaction failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount was debited but transaction failed",
      "Escalate to acquiring bank if terminal issue confirmed",
      "Retry transaction or suggest alternate payment mode",
      "Update transaction limits in CMS if limit issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Contactless Payment Not Working",
    "investigation_steps": [
      "Verify contactless feature status on card in CMS",
      "Check if card is NFC-enabled in CMS",
      "Retrieve POS transaction logs for contactless attempt",
      "Check error codes returned during contactless attempt",
      "Verify contactless transaction limit settings in CMS",
      "Check if merchant POS terminal supports contactless payments"
    ],
    "next_best_actions": [
      "Enable contactless feature on card in CMS if disabled",
      "Update contactless transaction limits if limit issue identified",
      "Escalate to card operations team if NFC chip issue suspected",
      "Initiate card replacement if physical NFC chip is damaged",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Tap to Pay Failed",
    "investigation_steps": [
      "Verify contactless/NFC feature status on card in CMS",
      "Retrieve POS transaction logs for tap-to-pay attempt",
      "Check error codes returned during tap-to-pay attempt",
      "Verify contactless transaction limit in CMS",
      "Check merchant terminal NFC compatibility",
      "Review switch logs for tokenization or NFC-related errors"
    ],
    "next_best_actions": [
      "Enable contactless feature on card in CMS if disabled",
      "Update contactless transaction limits if limit issue identified",
      "Escalate to card operations team if NFC chip failure suspected",
      "Initiate card replacement if physical NFC chip is damaged",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Online Transaction Failed",
    "investigation_steps": [
      "Retrieve online transaction logs from switch and payment gateway",
      "Check error codes returned during online transaction attempt",
      "Verify card status and online usage flag in CMS",
      "Verify account balance in CBS",
      "Review 3D Secure authentication logs",
      "Check OTP delivery logs and SMS gateway records",
      "Verify merchant payment gateway logs"
    ],
    "next_best_actions": [
      "Enable online usage on card in CMS if disabled",
      "Initiate reversal if amount was debited but transaction failed",
      "Escalate to payment gateway if gateway failure confirmed",
      "Update registered mobile number if OTP delivery failed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "International Transaction Declined",
    "investigation_steps": [
      "Verify international usage flag on card in CMS",
      "Retrieve transaction decline logs from switch",
      "Check decline reason code from payment network",
      "Verify account balance in CBS",
      "Check international transaction limits in CMS",
      "Verify merchant country and MCC details",
      "Review 3D Secure logs if card-not-present transaction"
    ],
    "next_best_actions": [
      "Enable international usage on card in CMS if disabled",
      "Update international transaction limits in CMS if limit issue identified",
      "Escalate to payment network if network-level decline identified",
      "Retry transaction after enabling/updating settings",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Domestic Transaction Declined",
    "investigation_steps": [
      "Retrieve transaction decline logs from switch",
      "Check decline reason code returned by switch or CBS",
      "Verify card status in CMS (active/blocked)",
      "Verify account balance in CBS",
      "Check domestic transaction limits in CMS",
      "Verify if specific channel (POS/ATM/online) is disabled in CMS"
    ],
    "next_best_actions": [
      "Unblock card in CMS if erroneously blocked",
      "Update transaction limits in CMS if limit issue identified",
      "Enable specific channel usage in CMS if disabled",
      "Escalate to CBS team if account-level issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Recurring Payment Failed",
    "investigation_steps": [
      "Retrieve recurring payment/standing instruction details from CBS",
      "Verify mandate registration status in NACH/e-mandate system",
      "Check account balance at time of recurring payment attempt",
      "Review decline reason from switch or payment gateway",
      "Verify card status and online usage flag in CMS",
      "Check merchant recurring payment setup"
    ],
    "next_best_actions": [
      "Retry recurring payment if balance/status issue resolved",
      "Re-register mandate if mandate issue identified",
      "Update card details for recurring payment if card was renewed",
      "Escalate to NACH/payment gateway team if systemic issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Merchant Payment Failed",
    "investigation_steps": [
      "Retrieve transaction logs from switch and payment gateway",
      "Check error codes returned during merchant payment attempt",
      "Verify card status and relevant channel usage flag in CMS",
      "Verify account balance in CBS",
      "Review merchant terminal/gateway logs",
      "Check if amount was debited despite payment failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount was debited but payment failed",
      "Escalate to acquiring bank or payment gateway if merchant-side issue identified",
      "Enable relevant channel on card in CMS if disabled",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Amount Debited but Merchant Not Credited",
    "investigation_steps": [
      "Retrieve transaction details from CBS and switch logs",
      "Verify debit posting in CBS",
      "Check settlement records with acquiring bank",
      "Verify NPCI/payment network settlement status",
      "Review reconciliation records for the transaction date",
      "Check acquiring bank's merchant credit records"
    ],
    "next_best_actions": [
      "Initiate settlement reconciliation with acquiring bank",
      "Escalate to NPCI if payment network settlement is pending",
      "Credit merchant account after settlement confirmation",
      "Reverse debit to customer if settlement cannot be completed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Amount Debited but Transaction Failed",
    "investigation_steps": [
      "Retrieve transaction logs from CBS and switch",
      "Verify debit posting in CBS",
      "Check switch logs for transaction failure reason",
      "Verify if reversal was auto-triggered by switch",
      "Check reconciliation records for pending reversal",
      "Review payment network settlement status"
    ],
    "next_best_actions": [
      "Initiate manual reversal in CBS if auto-reversal not triggered",
      "Escalate to switch/IT team if auto-reversal mechanism failed",
      "Reconcile transaction with payment network",
      "Credit customer account upon confirmed reversal",
      "Update CRM with reversal details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Duplicate Debit",
    "investigation_steps": [
      "Retrieve all debit transaction logs for the disputed date from CBS",
      "Verify if two separate debit entries exist for the same transaction",
      "Check switch logs for duplicate transaction processing",
      "Verify merchant transaction reference numbers for both debits",
      "Review reconciliation records for duplicate settlement",
      "Check acquiring bank records for duplicate authorization"
    ],
    "next_best_actions": [
      "Initiate reversal of duplicate debit in CBS",
      "Raise chargeback for duplicate charge with acquiring bank",
      "Escalate to switch/IT team if system-generated duplicate identified",
      "Reconcile duplicate settlement with payment network",
      "Update CRM with reversal details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Duplicate Transaction",
    "investigation_steps": [
      "Retrieve all transaction logs for disputed date from CBS and switch",
      "Verify if duplicate transaction reference numbers exist",
      "Check switch logs for duplicate authorization or settlement",
      "Verify merchant transaction records for both transactions",
      "Review reconciliation records for duplicate settlement"
    ],
    "next_best_actions": [
      "Initiate reversal of duplicate transaction in CBS",
      "Raise chargeback with acquiring bank for duplicate charge",
      "Escalate to switch/IT team if system-generated duplicate confirmed",
      "Reconcile with payment network",
      "Update CRM with reversal details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Double Charge on Same Transaction",
    "investigation_steps": [
      "Retrieve transaction logs for the disputed date from CBS and switch",
      "Verify if two charge entries exist against the same transaction reference",
      "Check switch logs and merchant terminal logs for double authorization",
      "Verify acquiring bank records for double settlement",
      "Review reconciliation records"
    ],
    "next_best_actions": [
      "Initiate reversal of one charge in CBS",
      "Raise chargeback with acquiring bank for the duplicate charge",
      "Escalate to switch/IT team if system-generated double charge confirmed",
      "Reconcile with payment network",
      "Update CRM with reversal details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Refund Not Received",
    "investigation_steps": [
      "Retrieve refund transaction details from CBS and switch",
      "Verify merchant refund initiation date and reference number",
      "Check payment network settlement records for refund credit",
      "Verify if refund was credited to correct account in CBS",
      "Review reconciliation records for pending refund credit",
      "Check acquiring bank records for refund processing status"
    ],
    "next_best_actions": [
      "Follow up with acquiring bank for refund credit confirmation",
      "Escalate to payment network if refund settlement is pending",
      "Credit customer account if refund settled but not posted in CBS",
      "Initiate reconciliation to trace and credit pending refund",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Refund Delayed",
    "investigation_steps": [
      "Retrieve refund initiation details from CBS and merchant records",
      "Verify refund processing status with acquiring bank",
      "Check payment network settlement cycle for refund",
      "Review reconciliation records for pending refund settlement",
      "Verify if refund was initiated by merchant within prescribed timelines"
    ],
    "next_best_actions": [
      "Follow up with acquiring bank for expedited refund processing",
      "Escalate to payment network if settlement is delayed beyond cycle",
      "Credit customer account upon settlement confirmation",
      "Update CRM with expected credit timeline",
      "Notify customer via SMS/email with updated refund timeline"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Merchant Refund Pending",
    "investigation_steps": [
      "Verify refund request initiation by merchant in payment gateway logs",
      "Check acquiring bank records for merchant refund processing status",
      "Verify payment network settlement cycle for merchant refunds",
      "Review CBS for any pending refund credit entries",
      "Confirm merchant refund reference number"
    ],
    "next_best_actions": [
      "Follow up with acquiring bank for merchant refund credit",
      "Escalate to payment network if refund settlement is pending",
      "Credit customer account upon confirmed refund settlement",
      "Update CRM with refund status and expected credit timeline"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Chargeback Not Processed",
    "investigation_steps": [
      "Verify chargeback request receipt in dispute management system",
      "Check chargeback filing status with payment network (NPCI/Visa/Mastercard)",
      "Verify if chargeback was filed within network-prescribed timelines",
      "Review dispute management system for processing errors",
      "Check acquiring bank response to chargeback"
    ],
    "next_best_actions": [
      "Refile chargeback if not processed within network timelines",
      "Escalate to payment network dispute desk",
      "Update dispute management system with corrective action",
      "Initiate provisional credit to customer account pending chargeback resolution",
      "Update CRM with chargeback filing details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Dispute Resolution Delay",
    "investigation_steps": [
      "Retrieve dispute filing details from dispute management system",
      "Check current status of dispute with payment network",
      "Verify acquiring bank response timeline",
      "Review internal dispute processing queue for bottlenecks",
      "Check if all required documentation was submitted for dispute"
    ],
    "next_best_actions": [
      "Escalate dispute to payment network for expedited resolution",
      "Follow up with acquiring bank for pending response",
      "Initiate provisional credit to customer account if not already done",
      "Update dispute management system with escalation details",
      "Update CRM with expected resolution timeline"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Declined at POS",
    "investigation_steps": [
      "Retrieve POS decline transaction logs from switch",
      "Check decline reason code from switch or payment network",
      "Verify card status in CMS (active/blocked)",
      "Verify account balance in CBS",
      "Check POS transaction limits in CMS",
      "Verify if POS usage is enabled on card in CMS",
      "Review acquiring bank terminal logs"
    ],
    "next_best_actions": [
      "Unblock card in CMS if erroneously blocked",
      "Enable POS usage on card in CMS if disabled",
      "Update POS transaction limits in CMS if limit issue identified",
      "Escalate to acquiring bank if terminal-level issue confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Declined Online",
    "investigation_steps": [
      "Retrieve online decline transaction logs from switch and payment gateway",
      "Check decline reason code",
      "Verify card status and online usage flag in CMS",
      "Verify account balance in CBS",
      "Check online transaction limits in CMS",
      "Review 3D Secure authentication logs",
      "Check OTP delivery logs"
    ],
    "next_best_actions": [
      "Enable online usage on card in CMS if disabled",
      "Update online transaction limits in CMS if limit issue identified",
      "Update registered mobile number if OTP delivery failed",
      "Escalate to payment gateway if gateway-level decline confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Not Supported by Merchant",
    "investigation_steps": [
      "Verify card network (Visa/Mastercard/RuPay) in CMS",
      "Check merchant's accepted card network from acquiring bank records",
      "Verify card variant and BIN range details",
      "Review switch logs for decline reason code related to card type",
      "Check if card has any network-level restrictions"
    ],
    "next_best_actions": [
      "Inform operations team of card network incompatibility",
      "Escalate to card operations team for network-level review",
      "Issue alternate network card if customer requires compatibility",
      "Update CRM with investigation findings"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Insufficient Balance Error Despite Available Funds",
    "investigation_steps": [
      "Verify account balance in CBS at time of transaction",
      "Check for any lien/hold on account balance in CBS",
      "Verify transaction amount against available (not ledger) balance",
      "Review switch logs for balance inquiry failure or stale balance data",
      "Check for any pending debits or uncleared instruments reducing available balance",
      "Verify CBS-switch balance synchronization"
    ],
    "next_best_actions": [
      "Release any erroneous lien or hold on account in CBS",
      "Escalate to CBS/IT team if balance synchronization issue identified",
      "Reconcile available balance in CBS",
      "Update CRM with corrective action taken",
      "Retry transaction after balance correction"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Daily Transaction Limit Issue",
    "investigation_steps": [
      "Verify daily transaction limit configured on card in CMS",
      "Check cumulative transaction amount for the day in CBS",
      "Review switch logs for limit breach decline",
      "Verify if limit was recently updated or reset in CMS",
      "Check RBI/NPCI prescribed limits for card variant"
    ],
    "next_best_actions": [
      "Update daily transaction limit in CMS per customer request and regulatory guidelines",
      "Reset daily limit counter if system error caused incorrect count",
      "Escalate to card operations team for limit configuration review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Transaction Limit Not Updated",
    "investigation_steps": [
      "Verify transaction limit update request in CRM and CMS",
      "Check CMS for current limit configuration on card",
      "Review CMS update logs for failure or pending status",
      "Verify if limit update request was within regulatory bounds",
      "Check system queue for pending limit update requests"
    ],
    "next_best_actions": [
      "Manually update transaction limit in CMS",
      "Escalate to CMS/IT team if system update failure identified",
      "Verify regulatory compliance of requested limit",
      "Update CRM with limit update confirmation",
      "Notify customer via SMS/email upon successful update"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "ATM Withdrawal Charge Dispute",
    "investigation_steps": [
      "Retrieve ATM withdrawal transaction and charge details from CBS",
      "Verify ATM operator and bank ownership (own bank vs other bank ATM)",
      "Check number of free transactions used in the month from CBS",
      "Verify applicable charge structure per RBI guidelines",
      "Review NPCI interchange settlement records for ATM charge",
      "Verify if charge was correctly applied per account type and ATM network"
    ],
    "next_best_actions": [
      "Reverse charge in CBS if incorrectly applied",
      "Escalate to ATM operations team if charge structure issue identified",
      "Reconcile NPCI interchange charge with CBS posting",
      "Update CRM with charge reversal or dispute resolution details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "POS Charge Dispute",
    "investigation_steps": [
      "Retrieve POS transaction and charge details from CBS",
      "Verify applicable POS charge structure for account type",
      "Check if POS charge was correctly applied per bank's fee schedule",
      "Review acquiring bank settlement records",
      "Verify if charge is a merchant surcharge or bank-imposed fee"
    ],
    "next_best_actions": [
      "Reverse charge in CBS if incorrectly applied",
      "Escalate to cards or operations team for fee structure review",
      "Reconcile POS charge with CBS posting",
      "Update CRM with charge reversal or dispute resolution details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "International Usage Not Enabled",
    "investigation_steps": [
      "Verify international usage flag on card in CMS",
      "Check if international usage enable request was received and processed",
      "Review CMS update logs for international usage flag",
      "Verify card variant's eligibility for international usage",
      "Check RBI guidelines compliance for international usage enablement"
    ],
    "next_best_actions": [
      "Enable international usage on card in CMS",
      "Escalate to card operations team if CMS update failure identified",
      "Notify customer via SMS/email upon enablement",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "International Usage Disabled Without Consent",
    "investigation_steps": [
      "Verify international usage flag status in CMS",
      "Check CMS audit logs for when and why international usage was disabled",
      "Verify if system auto-disable was triggered (fraud rule, regulatory)",
      "Review fraud management system for any auto-disable triggers",
      "Check if RBI/NPCI compliance rule triggered the disable"
    ],
    "next_best_actions": [
      "Re-enable international usage in CMS if disable was erroneous",
      "Escalate to fraud or compliance team if disable was system-triggered",
      "Notify customer via SMS/email with explanation and re-enablement confirmation",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Domestic Usage Disabled",
    "investigation_steps": [
      "Verify domestic usage flag on card in CMS",
      "Check CMS audit logs for when and why domestic usage was disabled",
      "Verify if system auto-disable was triggered",
      "Review fraud management system for auto-disable triggers",
      "Check if customer had previously requested domestic disable"
    ],
    "next_best_actions": [
      "Re-enable domestic usage on card in CMS",
      "Escalate to fraud or CMS team if system-triggered disable identified",
      "Notify customer via SMS/email upon re-enablement",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Online Usage Disabled",
    "investigation_steps": [
      "Verify online usage flag on card in CMS",
      "Check CMS audit logs for when and why online usage was disabled",
      "Verify if auto-disable was triggered by fraud rule or system",
      "Review fraud management system for auto-disable triggers",
      "Check if customer had previously requested online disable"
    ],
    "next_best_actions": [
      "Re-enable online usage on card in CMS",
      "Escalate to fraud or CMS team if system-triggered disable identified",
      "Notify customer via SMS/email upon re-enablement",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Contactless Usage Disabled",
    "investigation_steps": [
      "Verify contactless/NFC usage flag on card in CMS",
      "Check CMS audit logs for when and why contactless usage was disabled",
      "Verify if auto-disable was triggered by fraud rule or system",
      "Review fraud management system for auto-disable triggers",
      "Check if customer had previously requested contactless disable"
    ],
    "next_best_actions": [
      "Re-enable contactless usage on card in CMS",
      "Escalate to fraud or CMS team if system-triggered disable identified",
      "Notify customer via SMS/email upon re-enablement",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Linked Account Incorrect",
    "investigation_steps": [
      "Verify card-to-account mapping in CMS and CBS",
      "Check if card was linked to correct account at time of issuance",
      "Review CMS issuance records for account mapping error",
      "Check transaction history to identify impact of incorrect account linkage",
      "Verify if debits have occurred on incorrect account"
    ],
    "next_best_actions": [
      "Correct card-to-account mapping in CMS and CBS",
      "Reconcile any transactions posted to incorrect account",
      "Reverse and re-post transactions to correct account if applicable",
      "Escalate to card operations and CBS team for correction",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Wrong Account Debited",
    "investigation_steps": [
      "Retrieve transaction details from CBS",
      "Verify card-to-account mapping in CMS and CBS",
      "Identify which account was debited versus which should have been debited",
      "Check if multiple accounts are linked to the card",
      "Review switch logs for account routing"
    ],
    "next_best_actions": [
      "Reverse debit from incorrect account in CBS",
      "Post debit to correct account in CBS",
      "Correct card-to-account mapping in CMS if mapping error identified",
      "Escalate to CBS and card operations team",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Not Delivered",
    "investigation_steps": [
      "Verify card dispatch status in CMS",
      "Check courier tracking for card delivery status",
      "Verify dispatch address against CBS records",
      "Check if card was returned undelivered",
      "Confirm card issuance date and dispatch date"
    ],
    "next_best_actions": [
      "Initiate re-dispatch of card to verified address",
      "Update delivery address in CBS if incorrect",
      "Coordinate with courier partner for delivery",
      "Hotlist undelivered card if at risk of misuse",
      "Update CRM with re-dispatch details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Delivered to Wrong Address",
    "investigation_steps": [
      "Verify dispatch address used for card delivery in CMS",
      "Check CBS for current registered address of customer",
      "Verify if address mismatch was in CBS at time of dispatch",
      "Check courier delivery confirmation and delivery address",
      "Review CRM for any recent address change requests"
    ],
    "next_best_actions": [
      "Hotlist misdelivered card immediately in CMS",
      "Update correct address in CBS",
      "Initiate re-dispatch of new replacement card to correct address",
      "Escalate to card operations team for process review",
      "Update CRM with hotlisting and re-dispatch details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Dispatch Delay",
    "investigation_steps": [
      "Verify card dispatch request date in CMS",
      "Check card production and dispatch queue status",
      "Review courier partner dispatch logs",
      "Identify stage of delay: production, dispatch, or courier pickup",
      "Verify delivery address in CBS"
    ],
    "next_best_actions": [
      "Escalate to card production/dispatch team to expedite",
      "Coordinate with courier partner for priority dispatch",
      "Issue temporary virtual debit card if applicable",
      "Update CRM with expedited action details",
      "Notify customer via SMS/email with updated dispatch timeline"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Printing Delay",
    "investigation_steps": [
      "Verify card print request date in CMS",
      "Check card printing queue and production vendor logs",
      "Identify reason for printing delay (vendor issue, batch delay, etc.)",
      "Verify card data for printing accuracy in CMS",
      "Check production SLA adherence"
    ],
    "next_best_actions": [
      "Escalate to card production vendor for expedited printing",
      "Issue temporary virtual debit card if applicable",
      "Update CRM with production status",
      "Notify customer via SMS/email with updated timeline"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Issuance Delay",
    "investigation_steps": [
      "Verify card issuance request date and status in CMS",
      "Check if KYC and account opening formalities are complete in CBS",
      "Review card issuance queue for bottlenecks",
      "Check if any compliance or regulatory hold is preventing issuance",
      "Verify account eligibility for card issuance"
    ],
    "next_best_actions": [
      "Expedite card issuance in CMS if all eligibility criteria are met",
      "Escalate to compliance team if regulatory hold identified",
      "Complete pending KYC or account formalities if required",
      "Update CRM with issuance status and expected timeline"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Request Rejected",
    "investigation_steps": [
      "Verify card request rejection reason in CMS and CRM",
      "Check account eligibility criteria for card issuance in CBS",
      "Verify KYC status and account standing in CBS",
      "Check if any regulatory or internal policy restriction caused rejection",
      "Review card variant eligibility for the customer's account type"
    ],
    "next_best_actions": [
      "Re-process card request if rejection was due to system error",
      "Resolve eligibility or KYC issue and resubmit request",
      "Escalate to card operations or compliance team for policy review",
      "Update CRM with rejection reason and corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Upgrade Pending",
    "investigation_steps": [
      "Verify card upgrade request date and status in CMS",
      "Check eligibility for upgrade in CMS and CBS",
      "Review upgrade processing queue for delays",
      "Verify if old card hotlisting is pending post upgrade trigger",
      "Check card production and dispatch queue for upgraded card"
    ],
    "next_best_actions": [
      "Expedite upgrade processing in CMS",
      "Escalate to card operations team for manual processing",
      "Hotlist old card upon upgraded card dispatch",
      "Update CRM with upgrade status and expected timeline",
      "Notify customer via SMS/email upon upgrade completion"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Variant Change Pending",
    "investigation_steps": [
      "Verify variant change request date and status in CMS",
      "Check eligibility for requested variant in CBS",
      "Review variant change processing queue for delays",
      "Verify production and dispatch queue for new variant card",
      "Check if old card hotlisting is pending"
    ],
    "next_best_actions": [
      "Expedite variant change processing in CMS",
      "Escalate to card operations team for manual processing",
      "Hotlist old card upon new variant card dispatch",
      "Update CRM with variant change status and expected timeline",
      "Notify customer via SMS/email upon variant change completion"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Virtual Debit Card Not Generated",
    "investigation_steps": [
      "Verify virtual card generation request in CMS and mobile banking logs",
      "Check error codes during virtual card generation attempt",
      "Verify account eligibility for virtual debit card in CBS",
      "Review CMS/mobile banking API logs for generation failure",
      "Check if physical card is a prerequisite for virtual card generation"
    ],
    "next_best_actions": [
      "Retry virtual card generation in CMS",
      "Escalate to digital banking or CMS team if system failure identified",
      "Verify account eligibility and resolve any blocking conditions",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Virtual Debit Card Not Working",
    "investigation_steps": [
      "Verify virtual card status in CMS",
      "Check virtual card details (number, CVV, expiry) in CMS",
      "Retrieve transaction failure logs from switch and payment gateway",
      "Check error codes returned during virtual card usage",
      "Verify online usage flag for virtual card in CMS",
      "Review 3D Secure and OTP logs for virtual card transactions"
    ],
    "next_best_actions": [
      "Re-generate virtual card in CMS if card data issue identified",
      "Enable online usage on virtual card in CMS if disabled",
      "Escalate to digital banking or CMS team if system failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Virtual Card Expired Incorrectly",
    "investigation_steps": [
      "Verify virtual card expiry date in CMS",
      "Check CBS for correct expiry mapping for virtual card",
      "Review if premature expiry was triggered by system error in CMS",
      "Check switch logs for rejection due to expiry",
      "Verify if renewal virtual card was auto-generated"
    ],
    "next_best_actions": [
      "Correct virtual card expiry date in CMS if data error identified",
      "Re-generate virtual card with correct expiry if correction not possible",
      "Escalate to card operations or IT team for CMS data correction",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Replacement PIN Mailer Not Received",
    "investigation_steps": [
      "Verify replacement PIN mailer dispatch status in CMS",
      "Check courier tracking for PIN mailer delivery",
      "Verify dispatch address against CBS records",
      "Check if PIN mailer was returned undelivered",
      "Verify if green PIN option was triggered instead of mailer"
    ],
    "next_best_actions": [
      "Initiate green PIN generation via IVR or mobile banking as alternate",
      "Re-dispatch PIN mailer to verified address if electronic option unavailable",
      "Update delivery address in CBS if incorrect",
      "Coordinate with courier partner if mailer is in transit",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Closure Delay",
    "investigation_steps": [
      "Verify card closure request date and status in CMS",
      "Check CMS processing queue for pending closure requests",
      "Verify if any pending transactions or disputes are blocking closure",
      "Check if linked account closure is also pending in CBS",
      "Review compliance or regulatory hold on card closure"
    ],
    "next_best_actions": [
      "Process card closure in CMS manually",
      "Hotlist card pending formal closure",
      "Resolve pending transactions or disputes before closure",
      "Escalate to card operations team for expedited closure",
      "Update CRM with closure status"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Closure Not Processed",
    "investigation_steps": [
      "Verify card closure request in CMS and CRM",
      "Check CMS for current card status",
      "Review CMS logs for closure request processing failure",
      "Verify if technical failure caused request drop",
      "Check if card was used post closure request"
    ],
    "next_best_actions": [
      "Process card closure manually in CMS",
      "Hotlist card immediately if still active",
      "Escalate to CMS/IT team for closure processing failure investigation",
      "Update CRM with manual closure action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Still Active After Closure Request",
    "investigation_steps": [
      "Verify closure request timestamp in CRM and CMS",
      "Check CMS for current card status",
      "Review CMS logs for closure processing failure or delay",
      "Check switch logs for any transactions post closure request",
      "Verify if technical failure prevented closure processing"
    ],
    "next_best_actions": [
      "Hotlist and close card immediately in CMS",
      "Initiate chargeback for any unauthorized transactions post closure request",
      "Escalate to CMS/IT team for closure processing failure investigation",
      "Update CRM with immediate closure action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Linked to Closed Account",
    "investigation_steps": [
      "Verify card-to-account mapping in CMS and CBS",
      "Check account closure date in CBS",
      "Verify if card was hotlisted at time of account closure",
      "Review switch logs for any transactions attempted post account closure",
      "Check CMS for card status update upon account closure"
    ],
    "next_best_actions": [
      "Hotlist card immediately in CMS if still active",
      "Update card-to-account mapping in CMS to reflect account closure",
      "Escalate to card operations and CBS team for reconciliation",
      "Review account closure process to ensure card hotlisting is part of workflow",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Standing Instruction Failed",
    "investigation_steps": [
      "Retrieve standing instruction details from CBS",
      "Verify account balance at time of standing instruction execution",
      "Check CBS standing instruction processing logs for error codes",
      "Verify if card linked to standing instruction is active in CMS",
      "Check if standing instruction mandate is still valid",
      "Review if standing instruction parameters are correctly configured in CBS"
    ],
    "next_best_actions": [
      "Retry standing instruction execution if balance/status issue resolved",
      "Update standing instruction parameters in CBS if misconfigured",
      "Escalate to CBS team if system processing failure identified",
      "Notify relevant parties of failed standing instruction",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Auto-Debit Failed",
    "investigation_steps": [
      "Retrieve auto-debit/NACH mandate details from CBS",
      "Verify account balance at time of auto-debit execution",
      "Check NACH/e-mandate processing logs for failure reason",
      "Verify mandate registration and validity in NPCI NACH system",
      "Review CBS auto-debit processing logs for error codes",
      "Verify card and account status in CMS and CBS"
    ],
    "next_best_actions": [
      "Retry auto-debit if balance/status issue resolved",
      "Re-register NACH mandate if mandate issue identified",
      "Escalate to NPCI NACH team if systemic failure identified",
      "Notify destination party of auto-debit failure",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Subscription Payment Failed",
    "investigation_steps": [
      "Retrieve subscription payment details from payment gateway logs",
      "Verify card status and online usage flag in CMS",
      "Verify account balance in CBS at time of payment attempt",
      "Check 3D Secure and OTP logs for authentication failure",
      "Verify merchant's recurring payment mandate/token status",
      "Review payment gateway decline reason codes"
    ],
    "next_best_actions": [
      "Enable online usage on card in CMS if disabled",
      "Update card details with merchant for recurring payment",
      "Retry payment after resolving card/account issue",
      "Escalate to payment gateway if gateway failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Fuel Surcharge Reversal Not Received",
    "investigation_steps": [
      "Retrieve fuel transaction details from CBS",
      "Verify fuel surcharge amount posted in CBS",
      "Check applicable surcharge reversal policy and threshold",
      "Review NPCI or payment network settlement records for surcharge reversal",
      "Check reconciliation records for pending surcharge reversal credit",
      "Verify merchant MCC code to confirm fuel transaction"
    ],
    "next_best_actions": [
      "Initiate surcharge reversal credit in CBS if eligible",
      "Reconcile surcharge reversal with payment network",
      "Escalate to card operations team for surcharge reversal processing",
      "Update CRM with reversal details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Cash Withdrawal Declined Despite Sufficient Balance",
    "investigation_steps": [
      "Retrieve ATM transaction decline logs from switch",
      "Check decline reason code from switch or ATM",
      "Verify account balance and available balance in CBS",
      "Check for any lien or hold on account balance in CBS",
      "Verify ATM daily withdrawal limit in CMS",
      "Check if ATM was in online or offline mode",
      "Verify card status in CMS"
    ],
    "next_best_actions": [
      "Release any erroneous lien/hold on account in CBS",
      "Update ATM withdrawal limit in CMS if limit issue identified",
      "Escalate to ATM operations team if ATM-specific issue identified",
      "Escalate to CBS/IT team if balance synchronization issue confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Cash Withdrawal Pending",
    "investigation_steps": [
      "Retrieve ATM cash withdrawal transaction logs from CBS and switch",
      "Check if amount was debited from account in CBS",
      "Verify if ATM dispensed cash or showed dispense failure",
      "Review ATM cassette and dispense logs from ATM operations",
      "Check reconciliation records for pending ATM settlement",
      "Verify ATM cash balancing records"
    ],
    "next_best_actions": [
      "Initiate reversal in CBS if amount debited but cash not dispensed",
      "Escalate to ATM operations team for cassette and dispense log verification",
      "Reconcile ATM settlement with CBS",
      "Raise dispute with ATM operator if third-party ATM",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Balance Inquiry Failed",
    "investigation_steps": [
      "Retrieve balance inquiry failure logs from switch or mobile banking",
      "Check error codes returned during balance inquiry attempt",
      "Verify CBS connectivity and balance inquiry service availability",
      "Check if ATM or mobile banking channel was operational at time of inquiry",
      "Verify card status in CMS"
    ],
    "next_best_actions": [
      "Escalate to CBS/IT team if balance inquiry service failure identified",
      "Escalate to ATM operations team if ATM-specific issue confirmed",
      "Escalate to digital banking team if mobile banking channel issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Mini Statement Not Available",
    "investigation_steps": [
      "Retrieve mini statement request logs from ATM switch or mobile banking",
      "Check error codes during mini statement request",
      "Verify CBS transaction history service availability",
      "Check if ATM mini statement paper roll is functional (for ATM requests)",
      "Verify card status in CMS"
    ],
    "next_best_actions": [
      "Escalate to CBS/IT team if transaction history service failure identified",
      "Escalate to ATM operations team if ATM-specific issue confirmed",
      "Provide account statement via alternate channel (mobile banking, branch)",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Authentication Failed",
    "investigation_steps": [
      "Retrieve authentication failure logs from switch and CMS",
      "Check error codes returned during authentication failure",
      "Verify card status in CMS",
      "Check authentication method: PIN, OTP, biometric",
      "Review HSM logs for PIN verification failure",
      "Verify 3D Secure logs for card-not-present authentication failure"
    ],
    "next_best_actions": [
      "Reset card PIN if PIN authentication failure identified",
      "Update registered mobile number if OTP delivery failure identified",
      "Escalate to HSM/IT team if PIN verification system failure confirmed",
      "Escalate to 3D Secure service team if CNP authentication issue confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "3D Secure Authentication Failed",
    "investigation_steps": [
      "Retrieve 3D Secure authentication logs from payment gateway",
      "Check error codes returned during 3D Secure authentication",
      "Verify OTP delivery logs and SMS gateway records",
      "Check registered mobile number in CBS for OTP receipt",
      "Verify 3D Secure enrollment status of card in payment network",
      "Review payment gateway and issuer ACS logs"
    ],
    "next_best_actions": [
      "Update registered mobile number in CBS if OTP delivery failed",
      "Re-enroll card in 3D Secure if enrollment issue identified",
      "Escalate to payment gateway/ACS team if system failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "OTP Not Received for Debit Card Transaction",
    "investigation_steps": [
      "Verify OTP request logs from payment gateway and SMS gateway",
      "Check registered mobile number in CBS for OTP delivery",
      "Review SMS gateway delivery status and failure reason codes",
      "Verify if mobile number is DND (Do Not Disturb) registered",
      "Check SMS gateway provider logs for delivery failure",
      "Verify telecom carrier routing for the registered mobile number"
    ],
    "next_best_actions": [
      "Update registered mobile number in CBS if incorrect",
      "Escalate to SMS gateway provider if delivery failure confirmed",
      "Check and resolve DND registration if applicable",
      "Escalate to digital banking team for OTP service review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Registered Mobile Number Not Updated",
    "investigation_steps": [
      "Verify mobile number update request in CRM and CBS",
      "Check CBS for current registered mobile number",
      "Review CBS update logs for mobile number update failure or pending status",
      "Verify if update request went through proper authentication",
      "Check system queue for pending mobile number update requests"
    ],
    "next_best_actions": [
      "Manually update registered mobile number in CBS",
      "Escalate to CBS/IT team if system update failure identified",
      "Verify authentication and KYC for mobile number update",
      "Notify customer via old and new mobile number upon update",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Email ID Not Updated",
    "investigation_steps": [
      "Verify email ID update request in CRM and CBS",
      "Check CBS for current registered email ID",
      "Review CBS update logs for email update failure or pending status",
      "Verify if update request went through proper authentication",
      "Check system queue for pending email update requests"
    ],
    "next_best_actions": [
      "Manually update registered email ID in CBS",
      "Escalate to CBS/IT team if system update failure identified",
      "Notify customer via old and new email upon update",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Address Update Pending",
    "investigation_steps": [
      "Verify address update request in CRM and CBS",
      "Check CBS for current registered address",
      "Review CBS update logs for address update failure or pending status",
      "Verify if KYC documents were submitted for address change",
      "Check system queue for pending address update requests"
    ],
    "next_best_actions": [
      "Manually update registered address in CBS after KYC verification",
      "Escalate to KYC team if documents are pending review",
      "Update CRM with address change status",
      "Trigger card re-dispatch to updated address if card delivery was pending"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Name Correction Pending",
    "investigation_steps": [
      "Verify name correction request in CRM and CBS",
      "Check CBS for current name on account",
      "Review CBS update logs for name correction failure or pending status",
      "Verify if supporting KYC documents were submitted for name correction",
      "Check CMS for card name imprint details"
    ],
    "next_best_actions": [
      "Update name in CBS after KYC document verification",
      "Escalate to KYC team if documents are pending review",
      "Initiate card replacement with corrected name in CMS",
      "Update CRM with name correction status"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "KYC Pending for Debit Card",
    "investigation_steps": [
      "Verify KYC status in CBS and KYC management system",
      "Check which KYC documents are pending submission or verification",
      "Review KYC processing queue for pending customer records",
      "Check if KYC hold is blocking card issuance or usage",
      "Verify RBI KYC compliance status of account"
    ],
    "next_best_actions": [
      "Collect and process pending KYC documents",
      "Escalate to KYC team for expedited processing",
      "Update CBS with completed KYC status upon verification",
      "Release KYC hold on card after compliance confirmation",
      "Update CRM with KYC completion status"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Insurance Added Without Consent",
    "investigation_steps": [
      "Verify card insurance product details and activation date in CBS",
      "Check for customer consent record for insurance addition",
      "Review sales/operations logs for insurance enrollment",
      "Verify if insurance was bundled with card variant without explicit consent",
      "Check debit entries in CBS for insurance premium charges"
    ],
    "next_best_actions": [
      "Cancel card insurance product in CBS immediately",
      "Reverse any insurance premium charges from customer account",
      "Escalate to product/compliance team for unauthorized enrollment investigation",
      "Update CRM with cancellation and reversal details",
      "Report to compliance team for process review"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Debit Card Reward Points Not Credited",
    "investigation_steps": [
      "Verify reward points program eligibility for card variant in CMS",
      "Check reward points ledger for missing credit",
      "Retrieve eligible transaction details for reward points calculation",
      "Review reward points processing logs for the disputed transaction period",
      "Verify merchant MCC for reward points eligibility",
      "Check if reward program rules changed affecting credit"
    ],
    "next_best_actions": [
      "Manually credit reward points in reward management system",
      "Escalate to loyalty/reward program team for points reconciliation",
      "Verify and update reward program eligibility rules in CMS",
      "Update CRM with reward points credit details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Cashback Not Credited",
    "investigation_steps": [
      "Verify cashback offer eligibility for the transaction in CMS/offer management system",
      "Check cashback processing logs for the transaction",
      "Verify merchant MCC and transaction amount against cashback offer criteria",
      "Review reconciliation records for cashback settlement",
      "Check if cashback credit was posted to account in CBS"
    ],
    "next_best_actions": [
      "Manually credit cashback to customer account in CBS",
      "Escalate to offer management team for cashback processing review",
      "Reconcile cashback settlement with merchant/payment network",
      "Update CRM with cashback credit details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Offer Discount Not Applied",
    "investigation_steps": [
      "Verify offer eligibility for the transaction in offer management system",
      "Check offer terms and conditions against transaction details",
      "Verify merchant MCC, transaction amount, and channel against offer criteria",
      "Review payment gateway and switch logs for offer application attempt",
      "Check if offer was active at the time of transaction"
    ],
    "next_best_actions": [
      "Manually apply offer discount/credit to customer account if eligible",
      "Escalate to offer management team for offer application review",
      "Reconcile offer settlement with merchant/payment network",
      "Update CRM with offer credit details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Merchant Offer Not Applied",
    "investigation_steps": [
      "Verify merchant offer eligibility for the card variant in offer management system",
      "Check offer terms against transaction details (merchant, amount, channel)",
      "Review payment gateway logs for offer application at merchant",
      "Verify merchant's offer enrollment and registration in bank's offer system",
      "Check if offer was active at the time of transaction"
    ],
    "next_best_actions": [
      "Manually apply merchant offer benefit/credit to customer account if eligible",
      "Escalate to merchant partnerships or offer management team",
      "Coordinate with merchant's acquiring bank for offer settlement",
      "Update CRM with offer credit details"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Linked Wallet Payment Failed",
    "investigation_steps": [
      "Retrieve wallet payment transaction logs from wallet platform and switch",
      "Check error codes returned during wallet payment attempt",
      "Verify card linkage status in wallet platform",
      "Verify card status and online usage flag in CMS",
      "Check account balance in CBS",
      "Review payment gateway logs for wallet-to-card transaction failure"
    ],
    "next_best_actions": [
      "Re-link card to wallet if linkage issue identified",
      "Enable online usage on card in CMS if disabled",
      "Escalate to digital banking or wallet platform team if system failure confirmed",
      "Initiate reversal if amount was debited but payment failed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Verification Failed",
    "investigation_steps": [
      "Retrieve card verification failure logs from switch or payment gateway",
      "Check error codes returned during card verification",
      "Verify card details (number, CVV, expiry) in CMS",
      "Check if card is in active status in CMS",
      "Review 3D Secure verification logs if CNP transaction"
    ],
    "next_best_actions": [
      "Verify and correct card data in CMS if data mismatch identified",
      "Reissue card if card data integrity issue confirmed",
      "Escalate to card operations or IT team for verification system review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Tokenization Failed",
    "investigation_steps": [
      "Retrieve tokenization request logs from token service provider (TSP) or payment network",
      "Check error codes returned during tokenization attempt",
      "Verify card eligibility for tokenization in CMS",
      "Review TSP/payment network tokenization service logs",
      "Check if card is in active status in CMS",
      "Verify wallet/device requesting tokenization"
    ],
    "next_best_actions": [
      "Retry tokenization via TSP/payment network",
      "Escalate to TSP or payment network if tokenization service failure identified",
      "Verify card eligibility and resolve any blocking conditions",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Tokenized Card Not Working",
    "investigation_steps": [
      "Verify token status in TSP/payment network token vault",
      "Retrieve transaction failure logs from switch and wallet platform",
      "Check error codes returned during tokenized card transaction",
      "Verify token-to-card mapping in TSP records",
      "Check if card linked to token is active in CMS",
      "Review wallet platform logs for token usage failure"
    ],
    "next_best_actions": [
      "Refresh or re-provision token via TSP/payment network",
      "Escalate to TSP or payment network if token service failure confirmed",
      "Escalate to wallet platform team if wallet-side issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Removed from Wallet Automatically",
    "investigation_steps": [
      "Verify token status in TSP/payment network token vault",
      "Check TSP/wallet platform logs for token deletion or suspension",
      "Identify reason for automatic removal (card expiry, card block, fraud flag, wallet policy)",
      "Verify card status in CMS (active/blocked/expired)",
      "Review wallet platform audit logs for removal event"
    ],
    "next_best_actions": [
      "Re-provision card token to wallet if removal was erroneous",
      "Escalate to TSP or wallet platform team if auto-removal was system error",
      "Update card in wallet after card renewal if removed due to expiry",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Usage Notification Not Received",
    "investigation_steps": [
      "Verify transaction alert configuration in CBS/notification system",
      "Check SMS/email gateway delivery logs for the disputed transaction alert",
      "Verify registered mobile number and email ID in CBS",
      "Check if SMS/email notification service was active at time of transaction",
      "Verify if customer's mobile number is DND registered",
      "Review notification system logs for delivery failure"
    ],
    "next_best_actions": [
      "Update registered mobile number/email in CBS if incorrect",
      "Escalate to SMS/email gateway provider if delivery failure confirmed",
      "Check and resolve DND registration if applicable",
      "Escalate to notification/digital banking team for service review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "SMS Alert Not Received",
    "investigation_steps": [
      "Verify SMS alert configuration in CBS/notification system",
      "Check SMS gateway delivery logs for the disputed alert",
      "Verify registered mobile number in CBS",
      "Check if SMS service was active at time of event",
      "Verify if mobile number is DND registered",
      "Review telecom carrier routing for the registered number",
      "Check SMS gateway provider logs for delivery failure reason"
    ],
    "next_best_actions": [
      "Update registered mobile number in CBS if incorrect",
      "Escalate to SMS gateway provider if delivery failure confirmed",
      "Check and resolve DND registration if applicable",
      "Escalate to notification/digital banking team for SMS service review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Debit Card",
    "sub_issue": "Card Misused After Blocking",
    "investigation_steps": [
      "Verify card block timestamp in CMS",
      "Retrieve all transaction logs post block request from switch",
      "Check CMS for card status at time of disputed transactions",
      "Verify if block was processed before disputed transactions occurred",
      "Review switch logs to confirm card was rejected post block",
      "Check if any transactions were pre-authorized before block and settled post block"
    ],
    "next_best_actions": [
      "Initiate chargeback for all transactions occurring after confirmed block timestamp",
      "Escalate to fraud management team for investigation",
      "Escalate to CMS/IT team if card transactions were processed despite active block",
      "Initiate provisional credit to customer account",
      "Update CRM with chargeback and investigation details"
    ]
  }
],
[
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Not Dispensed but Account Debited",
    "investigation_steps": [
      "Check CBS transaction log for debit entry",
      "Verify ATM switch/EJ (Electronic Journal) log for dispense response code",
      "Check NPCI/network switch transaction status for the same RRN",
      "Verify cash counter/sensor log at the ATM for actual cash-out confirmation",
      "Cross-check vendor/acquirer TC51/TC53 reconciliation file"
    ],
    "next_best_actions": [
      "Initiate auto-reversal if no dispense confirmation found",
      "Credit provisional refund as per RBI TAT",
      "Raise chargeback/representment via NPCI if disputed",
      "Update CBS ledger and close reversal",
      "Reconcile entry in settlement file"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Partial Cash Dispensed",
    "investigation_steps": [
      "Check EJ log for cash dispensed count vs requested amount",
      "Verify cash cassette sensor count at ATM",
      "Check CBS debit amount against actual dispensed amount",
      "Review vendor cash replenishment and jam logs"
    ],
    "next_best_actions": [
      "Credit the shortfall amount to customer account",
      "Update CBS records to reflect corrected debit",
      "Flag ATM for cassette/sensor inspection",
      "Reconcile cash difference with vendor cash management report"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Wrong Amount Dispensed",
    "investigation_steps": [
      "Check EJ log for denomination and count dispensed",
      "Compare requested transaction amount with CBS debit amount",
      "Verify cassette loading/denomination mapping configuration",
      "Check switch log for transaction amount field mismatch"
    ],
    "next_best_actions": [
      "Initiate reversal/adjustment for incorrect amount",
      "Correct cassette denomination mapping",
      "Update CBS records",
      "Escalate to ATM vendor for cassette configuration fix"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Excess Cash Dispensed",
    "investigation_steps": [
      "Check EJ log and cash counter sensor reading for over-dispense",
      "Verify CBS debit amount versus actual cash dispensed",
      "Review cassette denomination configuration for incorrect note value loading",
      "Check vendor cash loading/replenishment records"
    ],
    "next_best_actions": [
      "Raise recovery/debit adjustment for excess amount dispensed",
      "Correct cassette denomination configuration",
      "Update CBS records",
      "Flag ATM for vendor cash audit"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Withdrawal Failed",
    "investigation_steps": [
      "Check CBS authorization response code",
      "Verify switch/NPCI transaction status and response code",
      "Review EJ log for terminal-level error",
      "Check network connectivity logs for the ATM at transaction timestamp"
    ],
    "next_best_actions": [
      "Initiate reversal if debit occurred without dispense",
      "Retry transaction processing if technical decline",
      "Update CBS records",
      "Escalate to network/switch team if recurring"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Withdrawal Pending",
    "investigation_steps": [
      "Check transaction status in switch/NPCI queue",
      "Verify CBS hold/pending entry against the transaction",
      "Review EJ log for terminal response timeout",
      "Check settlement file for matching entry"
    ],
    "next_best_actions": [
      "Auto-reverse pending transaction post TAT",
      "Update CBS to release hold",
      "Reconcile with settlement file",
      "Escalate unresolved pending entries to NPCI"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Withdrawal Declined Despite Sufficient Balance",
    "investigation_steps": [
      "Verify account balance and hold/lien amount in CBS at transaction timestamp",
      "Check switch response code for decline reason",
      "Review daily withdrawal limit and per-transaction limit configuration",
      "Check card status (block/hotlist) at the time of transaction"
    ],
    "next_best_actions": [
      "Correct lien/hold mapping in CBS if incorrect",
      "Update limit configuration if misconfigured",
      "Unblock card if erroneously restricted",
      "Communicate decline reason code resolution to relevant system"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Card Retained",
    "investigation_steps": [
      "Check EJ log for card retention event code",
      "Verify ATM card retention bin/cassette log",
      "Cross-check card retention reason (hotlisted, expired, mechanical fault)",
      "Review CCTV/surveillance log for retention incident if required"
    ],
    "next_best_actions": [
      "Initiate card retrieval from ATM cassette/retention bin",
      "Hotlist or reissue card based on retention reason",
      "Update card status in CBS",
      "Dispatch retained card to issuing branch for return"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Card Not Returned",
    "investigation_steps": [
      "Check EJ log for card return/eject confirmation",
      "Verify retention bin log for retained card count",
      "Review CCTV footage if available for the transaction timestamp"
    ],
    "next_best_actions": [
      "Retrieve card from retention bin if found",
      "Block/hotlist card as precaution",
      "Issue replacement card",
      "Update CBS card status records"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Card Stuck",
    "investigation_steps": [
      "Check EJ log for card reader mechanical error code",
      "Review ATM card reader maintenance/fault log",
      "Verify retention bin status for the stuck card"
    ],
    "next_best_actions": [
      "Dispatch field engineer for card reader inspection",
      "Retrieve and return card if recovered",
      "Block card as precaution and reissue if not recovered",
      "Flag ATM card reader for maintenance"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM PIN Change Failed",
    "investigation_steps": [
      "Check CBS PIN change request log and response code",
      "Verify switch/HSM log for PIN change transaction status",
      "Review EJ log for terminal-level error during PIN change"
    ],
    "next_best_actions": [
      "Retry PIN change request through alternate channel",
      "Reset PIN generation request in CBS",
      "Escalate to HSM/security team if encryption-related failure",
      "Update CBS PIN status flag"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM PIN Generation Failed",
    "investigation_steps": [
      "Check CBS Green PIN/PIN generation request log",
      "Verify HSM response code for PIN generation request",
      "Review SMS/OTP gateway log if OTP-based PIN generation used"
    ],
    "next_best_actions": [
      "Re-trigger PIN generation request",
      "Escalate to HSM team if cryptographic failure",
      "Verify and correct mobile number/OTP delivery mapping",
      "Update CBS PIN issuance status"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM PIN Reset Failed",
    "investigation_steps": [
      "Check CBS PIN reset request status",
      "Verify HSM/switch log for reset transaction response",
      "Review OTP/authentication log used for PIN reset verification"
    ],
    "next_best_actions": [
      "Re-initiate PIN reset process",
      "Escalate to HSM team for cryptographic failure",
      "Correct authentication mapping if verification failed incorrectly",
      "Update CBS PIN status flag"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Incorrect PIN Accepted",
    "investigation_steps": [
      "Check switch/HSM authentication log for the transaction",
      "Verify CBS PIN validation response for the session",
      "Review card authentication and PIN verification configuration",
      "Check for HSM key mismatch or PIN block translation error"
    ],
    "next_best_actions": [
      "Escalate to HSM/security team for immediate investigation",
      "Block affected card(s) as precaution",
      "Correct PIN validation/key configuration",
      "Report finding to fraud risk and security teams"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Balance Inquiry Failed",
    "investigation_steps": [
      "Check switch response code for balance inquiry request",
      "Verify CBS account status and connectivity logs",
      "Review EJ log for terminal-level error during inquiry"
    ],
    "next_best_actions": [
      "Retry balance inquiry routing",
      "Escalate to switch/network team if recurring",
      "Update CBS connectivity configuration if required",
      "Verify account status correction if flagged incorrectly"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Mini Statement Not Printed",
    "investigation_steps": [
      "Check EJ log for printer command and response status",
      "Verify ATM printer hardware fault/paper-out log",
      "Review CBS mini-statement data retrieval response"
    ],
    "next_best_actions": [
      "Dispatch field engineer for printer maintenance",
      "Replenish printer paper roll",
      "Retry mini-statement request",
      "Flag ATM for printer hardware audit"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Receipt Not Printed",
    "investigation_steps": [
      "Check EJ log for receipt print command status",
      "Verify printer hardware/paper-out fault log",
      "Confirm transaction completion status independent of receipt printing"
    ],
    "next_best_actions": [
      "Dispatch field engineer for printer fault rectification",
      "Replenish receipt paper",
      "Provide duplicate transaction confirmation if required",
      "Flag ATM for printer maintenance"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Receipt Shows Incorrect Transaction",
    "investigation_steps": [
      "Compare printed receipt data against EJ log transaction record",
      "Verify CBS transaction record for the same RRN/timestamp",
      "Check printer buffer/queue for data mismatch or stale cache"
    ],
    "next_best_actions": [
      "Correct printer data buffer/template configuration",
      "Reconcile actual transaction with CBS records",
      "Escalate to vendor for printer firmware/template fix",
      "Issue corrected transaction confirmation if required"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Screen Frozen",
    "investigation_steps": [
      "Check ATM terminal health/heartbeat monitoring log",
      "Review EJ log for last transaction before freeze",
      "Verify hardware/software crash log on ATM terminal"
    ],
    "next_best_actions": [
      "Remote restart ATM terminal",
      "Dispatch field engineer if remote restart fails",
      "Verify and reverse any incomplete transaction caused by freeze",
      "Flag ATM for software/hardware diagnostic"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Touchscreen Not Working",
    "investigation_steps": [
      "Check terminal hardware fault log for touchscreen component",
      "Review ATM health monitoring dashboard for device status",
      "Verify calibration log of touchscreen interface"
    ],
    "next_best_actions": [
      "Dispatch field engineer for touchscreen repair/replacement",
      "Take ATM offline until rectified",
      "Recalibrate touchscreen if required",
      "Flag ATM for hardware maintenance"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Machine Out of Service",
    "investigation_steps": [
      "Check ATM monitoring dashboard for terminal status code",
      "Verify last heartbeat/connectivity log",
      "Review maintenance ticket history for the ATM",
      "Check vendor field service log for ongoing issue"
    ],
    "next_best_actions": [
      "Escalate to field service/vendor team for restoration",
      "Mark ATM as out-of-service in ATM locator system",
      "Schedule preventive maintenance",
      "Update ATM status in CBS/network monitoring system"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Power Failure During Transaction",
    "investigation_steps": [
      "Check EJ log for transaction status before power loss",
      "Verify UPS/power backup log at ATM site",
      "Cross-check CBS transaction status against terminal log"
    ],
    "next_best_actions": [
      "Reverse any incomplete debit caused by power failure",
      "Escalate to facility/vendor team for power backup inspection",
      "Update CBS records post-reconciliation",
      "Flag site for power infrastructure review"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Network Error",
    "investigation_steps": [
      "Check ATM-to-switch connectivity/network log",
      "Verify network latency/timeout logs at transaction timestamp",
      "Review switch/host response time for the affected session"
    ],
    "next_best_actions": [
      "Escalate to network operations team for connectivity restoration",
      "Reroute ATM to backup network link if available",
      "Reverse failed transactions caused by network drop",
      "Monitor ATM connectivity post-fix"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Session Timed Out",
    "investigation_steps": [
      "Check EJ log for session duration and timeout trigger",
      "Verify switch/host response latency for the session",
      "Review terminal application timeout configuration"
    ],
    "next_best_actions": [
      "Reverse any debit linked to timed-out session",
      "Adjust timeout threshold configuration if misconfigured",
      "Escalate to application/switch team if recurring",
      "Retry transaction processing"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Camera Not Working",
    "investigation_steps": [
      "Check CCTV/ATM camera health monitoring log",
      "Verify DVR/recording system status for the ATM site",
      "Review maintenance ticket history for camera unit"
    ],
    "next_best_actions": [
      "Dispatch field engineer for camera repair/replacement",
      "Escalate to security infrastructure team",
      "Flag ATM for surveillance system audit",
      "Update camera maintenance schedule"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Security Concern",
    "investigation_steps": [
      "Review CCTV footage and ATM security log for the reported concern",
      "Check ATM site security infrastructure (lighting, guard logs, alarm system)",
      "Verify any prior security incident reports for the location"
    ],
    "next_best_actions": [
      "Escalate to security/risk team for site assessment",
      "Arrange additional security measures at ATM site",
      "Coordinate with law enforcement if required",
      "Update ATM risk register"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Skimming Fraud",
    "investigation_steps": [
      "Inspect ATM card reader/PIN pad for skimming device",
      "Review CCTV footage for suspicious device installation activity",
      "Check fraud monitoring system for affected card transaction patterns",
      "Cross-verify with NPCI/network fraud alerts for the terminal"
    ],
    "next_best_actions": [
      "Take ATM offline immediately for forensic inspection",
      "Block/hotlist all potentially compromised cards",
      "Escalate to fraud risk and law enforcement",
      "Reissue cards to affected customers and reverse fraudulent transactions"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Card Cloning at ATM",
    "investigation_steps": [
      "Review fraud monitoring alerts for cloned card usage pattern",
      "Check ATM site for skimming device evidence",
      "Verify transaction geography/velocity anomalies in fraud system",
      "Cross-check with NPCI fraud reporting for affected BIN/terminal"
    ],
    "next_best_actions": [
      "Block cloned card(s) immediately",
      "Reverse unauthorized transactions per dispute process",
      "Escalate to fraud investigation team and law enforcement",
      "Reissue card with EMV chip if not already issued"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Unauthorized ATM Withdrawal",
    "investigation_steps": [
      "Check CBS transaction log and card usage history",
      "Verify EJ log and CCTV footage for the disputed transaction",
      "Review fraud monitoring system alerts for the account",
      "Check card status (block date/time) versus transaction timestamp"
    ],
    "next_best_actions": [
      "Block card immediately if not already done",
      "Raise dispute/chargeback through NPCI if applicable",
      "Provisionally credit account per RBI liability guidelines pending investigation",
      "Escalate to fraud investigation team"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Fraudulent ATM Transaction",
    "investigation_steps": [
      "Review fraud monitoring system flags for the transaction",
      "Check CCTV footage and EJ log for transaction details",
      "Verify card/PIN compromise indicators (skimming, phishing) for the account",
      "Cross-check NPCI fraud advisory for the terminal/BIN"
    ],
    "next_best_actions": [
      "Block card and freeze further suspicious transactions",
      "Initiate dispute/chargeback process",
      "Escalate to fraud risk and law enforcement",
      "Process provisional credit as per regulatory timelines pending investigation outcome"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Cash Deposit Failed",
    "investigation_steps": [
      "Check EJ log for deposit transaction status",
      "Verify cash acceptor/note validator hardware log",
      "Check CBS for any provisional credit entry"
    ],
    "next_best_actions": [
      "Reverse any erroneous debit/hold if applicable",
      "Retry deposit transaction processing",
      "Escalate to vendor for cash acceptor hardware check",
      "Update CBS records"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit Pending",
    "investigation_steps": [
      "Check CDM cash-in transaction status in switch/CBS queue",
      "Verify EJ log for note count and acceptance confirmation",
      "Review cash management/vault reconciliation report"
    ],
    "next_best_actions": [
      "Credit account post verification of cash-in count",
      "Escalate to cash management team for vault reconciliation",
      "Update CBS to close pending entry",
      "Notify customer support team of resolution status"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposited but Not Credited",
    "investigation_steps": [
      "Check EJ log for note acceptance and count confirmation",
      "Cross-verify CDM cash-in count against vault/cash management reconciliation report",
      "Verify CBS for missing credit entry against transaction reference"
    ],
    "next_best_actions": [
      "Credit account based on verified cash-in count",
      "Update CBS records and close discrepancy",
      "Reconcile with vault cash management report",
      "Escalate to ATM/CDM vendor if hardware count mismatch found"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Partial Cash Deposit Credited",
    "investigation_steps": [
      "Check EJ log for total notes accepted versus credited amount",
      "Verify note validator rejection log for partially accepted notes",
      "Cross-check CBS credit entry against vault reconciliation"
    ],
    "next_best_actions": [
      "Credit shortfall amount after verification",
      "Update CBS records",
      "Escalate to vendor for note validator calibration check",
      "Reconcile cash variance with vault report"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cheque Deposit Failed",
    "investigation_steps": [
      "Check EJ log for cheque scanning/processing status",
      "Verify cheque image capture log at the ATM/CDM",
      "Check CBS for any provisional entry against the cheque deposit"
    ],
    "next_best_actions": [
      "Retry cheque deposit processing if image capture failed",
      "Reverse provisional entry if transaction not completed",
      "Escalate to cheque processing/CTS team if applicable",
      "Advise re-deposit through alternate channel if unresolved"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cheque Deposited but Not Updated",
    "investigation_steps": [
      "Check EJ log for cheque image capture confirmation",
      "Verify cheque clearing/CTS system status for the cheque reference",
      "Cross-check CBS for credit entry against the cheque deposit"
    ],
    "next_best_actions": [
      "Update CBS with credit entry post verification",
      "Escalate to cheque clearing team for status tracking",
      "Reconcile cheque deposit log with CTS records",
      "Communicate resolution status to relevant teams"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cheque Deposit Pending",
    "investigation_steps": [
      "Check cheque clearing cycle status in CTS/clearing system",
      "Verify EJ log for cheque acceptance confirmation",
      "Cross-check CBS for hold/pending credit entry"
    ],
    "next_best_actions": [
      "Monitor and update CBS upon clearing confirmation",
      "Escalate to clearing operations team if delayed beyond cycle",
      "Reconcile with CTS settlement records",
      "Release hold once cheque is cleared"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "CDM Not Accepting Cash",
    "investigation_steps": [
      "Check note validator/cash acceptor hardware fault log",
      "Review EJ log for repeated rejection error codes",
      "Verify cassette/bunch note feeder mechanical status"
    ],
    "next_best_actions": [
      "Dispatch field engineer for note validator inspection",
      "Take CDM offline until rectified",
      "Flag for vendor hardware maintenance",
      "Update CDM status in monitoring dashboard"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "CDM Cash Jam",
    "investigation_steps": [
      "Check EJ log for jam error code and timestamp",
      "Review note transport mechanism fault log",
      "Verify cassette/bin status for stuck notes"
    ],
    "next_best_actions": [
      "Dispatch field engineer to clear jam",
      "Take CDM offline until cleared",
      "Reconcile any partially processed cash-in transaction",
      "Flag CDM for mechanical maintenance"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "CDM Receipt Not Generated",
    "investigation_steps": [
      "Check EJ log for receipt print command status",
      "Verify printer hardware/paper-out fault log",
      "Confirm transaction completion status independent of receipt printing"
    ],
    "next_best_actions": [
      "Dispatch field engineer for printer fault rectification",
      "Replenish receipt paper",
      "Provide duplicate transaction confirmation if required",
      "Flag CDM for printer maintenance"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Deposit Receipt Missing",
    "investigation_steps": [
      "Check EJ log for receipt print confirmation against deposit transaction",
      "Verify printer fault/paper-out log at transaction timestamp",
      "Cross-check CBS deposit entry independent of receipt"
    ],
    "next_best_actions": [
      "Issue duplicate transaction confirmation/receipt",
      "Update printer maintenance log",
      "Reconcile transaction with CBS records",
      "Flag machine for printer hardware check"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Dispensed Fake Currency",
    "investigation_steps": [
      "Verify cash cassette loading/replenishment audit trail and vendor custody chain",
      "Cross-check currency verification machine (CVM) records used during cassette loading",
      "Review CCTV footage for cassette loading/replenishment process",
      "Escalate note for forensic verification"
    ],
    "next_best_actions": [
      "Replace counterfeit currency with genuine notes for the customer",
      "Escalate to currency chest/vendor cash management team for audit",
      "Report incident to RBI/law enforcement as per regulatory norms",
      "Flag cassette/vendor for cash quality audit"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Dispensed Damaged Notes",
    "investigation_steps": [
      "Check cassette loading/quality control log for note condition checks",
      "Review currency verification machine records prior to loading",
      "Verify vendor cash replenishment quality audit trail"
    ],
    "next_best_actions": [
      "Exchange damaged notes for the customer per RBI note exchange guidelines",
      "Escalate to cash management team for quality control review",
      "Flag cassette for vendor audit",
      "Update cash quality SOP compliance check"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Dispensed Torn Notes",
    "investigation_steps": [
      "Check cassette loading/quality control log for note condition checks",
      "Review currency verification machine records prior to loading",
      "Verify vendor cash replenishment quality audit trail"
    ],
    "next_best_actions": [
      "Exchange torn notes for the customer per RBI note exchange guidelines",
      "Escalate to cash management team for quality control review",
      "Flag cassette for vendor audit",
      "Update cash quality SOP compliance check"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Dispensed Soiled Notes",
    "investigation_steps": [
      "Check cassette loading/quality control log for note condition checks",
      "Review currency verification machine records prior to loading",
      "Verify vendor cash replenishment quality audit trail"
    ],
    "next_best_actions": [
      "Exchange soiled notes for the customer per RBI note exchange guidelines",
      "Escalate to cash management team for quality control review",
      "Flag cassette for vendor audit",
      "Update cash quality SOP compliance check"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Dispensed in Wrong Denomination",
    "investigation_steps": [
      "Check cassette denomination mapping configuration",
      "Verify EJ log for denomination dispensed versus configured cassette setting",
      "Review vendor cassette loading log for misloading"
    ],
    "next_best_actions": [
      "Correct cassette denomination mapping immediately",
      "Reconcile cash variance with vendor cash management report",
      "Escalate to vendor for cassette loading audit",
      "Update terminal configuration records"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Running Out of Cash Frequently",
    "investigation_steps": [
      "Review cash replenishment frequency and cash forecast model for the ATM",
      "Check historical cash-out incident log and withdrawal volume trend",
      "Verify vendor cash management SLA compliance"
    ],
    "next_best_actions": [
      "Revise cash replenishment schedule/forecast for the ATM",
      "Escalate to cash management/vendor team for increased replenishment frequency",
      "Update cash forecast model parameters",
      "Monitor cash levels post-correction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Not Dispensing Cash",
    "investigation_steps": [
      "Check cash dispenser hardware fault log",
      "Verify cassette/sensor status for cash availability",
      "Review EJ log for dispense mechanism error code"
    ],
    "next_best_actions": [
      "Dispatch field engineer for dispenser hardware repair",
      "Take ATM offline until rectified",
      "Reverse any debit without dispense",
      "Flag ATM for vendor hardware maintenance"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Withdrawal Reversed Incorrectly",
    "investigation_steps": [
      "Check CBS reversal entry against original transaction record",
      "Verify switch/NPCI reversal message log",
      "Cross-check EJ log for actual dispense status"
    ],
    "next_best_actions": [
      "Correct reversal entry in CBS",
      "Re-debit or re-credit account based on verified actual transaction outcome",
      "Reconcile with settlement file",
      "Escalate to switch team if reversal message error identified"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Amount Debited Twice",
    "investigation_steps": [
      "Check CBS for duplicate debit entries against same transaction reference",
      "Verify switch/NPCI log for duplicate authorization message",
      "Cross-check EJ log for single dispense event"
    ],
    "next_best_actions": [
      "Reverse the duplicate debit entry",
      "Update CBS records",
      "Raise chargeback/representment via NPCI if required",
      "Reconcile with settlement file"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Duplicate ATM Withdrawal",
    "investigation_steps": [
      "Check CBS for multiple debit entries against single customer-initiated request",
      "Verify switch retransmission/timeout retry logs",
      "Cross-check EJ log for actual number of dispense events"
    ],
    "next_best_actions": [
      "Reverse the duplicate transaction amount",
      "Update CBS records",
      "Escalate to switch team to prevent retry duplication",
      "Reconcile with settlement file"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Duplicate Debit for Single Withdrawal",
    "investigation_steps": [
      "Check CBS for multiple debit entries against single transaction reference",
      "Verify switch/NPCI message log for retransmission",
      "Cross-check EJ log for single dispense confirmation"
    ],
    "next_best_actions": [
      "Reverse the duplicate debit",
      "Update CBS records",
      "Raise representment via NPCI if needed",
      "Reconcile settlement records"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Refund Not Received After ATM Failure",
    "investigation_steps": [
      "Check CBS reversal/refund entry status against the failed transaction",
      "Verify TAT compliance for auto-reversal process",
      "Cross-check settlement/reconciliation file for pending refund entries"
    ],
    "next_best_actions": [
      "Process pending refund/reversal immediately",
      "Update CBS records",
      "Escalate to reconciliation team for unresolved entries",
      "Report TAT breach internally for process correction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Dispute Not Resolved",
    "investigation_steps": [
      "Review dispute case history and prior investigation notes",
      "Check CBS, EJ log, and NPCI dispute status for pending action",
      "Verify chargeback/representment cycle status with NPCI"
    ],
    "next_best_actions": [
      "Reassign and expedite pending investigation steps",
      "Process resolution (credit/reject) based on investigation outcome",
      "Update dispute case status in tracking system",
      "Escalate to next level if dispute remains unresolved beyond cycle"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Charge Dispute",
    "investigation_steps": [
      "Check CBS for the disputed charge entry and applicable fee schedule",
      "Verify charge computation against approved tariff/fee structure",
      "Review transaction log for fee trigger conditions"
    ],
    "next_best_actions": [
      "Reverse incorrect charge if fee misapplied",
      "Update CBS fee configuration if systemic error found",
      "Reconcile fee income ledger",
      "Communicate correction to relevant processing team"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Foreign ATM Withdrawal Charge Dispute",
    "investigation_steps": [
      "Check CBS for foreign transaction markup/fee entry and applicable card scheme tariff",
      "Verify exchange rate and conversion markup applied versus card network rate",
      "Review card scheme (Visa/Mastercard/NPCI international) settlement advice"
    ],
    "next_best_actions": [
      "Reverse incorrect markup/fee if miscalculated",
      "Update CBS forex fee configuration",
      "Reconcile with card network settlement report",
      "Escalate to card network team if rate discrepancy persists"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Interchange Fee Charged Incorrectly",
    "investigation_steps": [
      "Check NPCI/card network interchange fee settlement file for the transaction",
      "Verify interchange fee configuration against applicable NPCI/network tariff",
      "Cross-check CBS fee ledger entry against settlement advice"
    ],
    "next_best_actions": [
      "Correct interchange fee entry in CBS",
      "Raise dispute with NPCI/network for settlement correction",
      "Reconcile settlement file post-correction",
      "Update fee configuration to prevent recurrence"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Convenience Fee Incorrect",
    "investigation_steps": [
      "Check CBS convenience fee entry against approved fee schedule",
      "Verify fee configuration mapping for off-us/on-us transaction type",
      "Review transaction log for fee trigger condition"
    ],
    "next_best_actions": [
      "Reverse incorrect convenience fee charged",
      "Update fee configuration mapping",
      "Reconcile fee income ledger",
      "Communicate correction to switch/fee configuration team"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Transaction History Missing",
    "investigation_steps": [
      "Check CBS transaction log retrieval query for the account",
      "Verify switch/EJ log archival and retention status",
      "Cross-check data sync between core banking and statement/history module"
    ],
    "next_best_actions": [
      "Restore missing transaction entries from archival/backup logs",
      "Escalate to IT/data team for sync issue resolution",
      "Update CBS transaction history records",
      "Verify resolution by re-querying transaction history"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Transaction History Incorrect",
    "investigation_steps": [
      "Compare displayed transaction history against CBS source records",
      "Verify EJ log and switch log for actual transaction details",
      "Check statement/history module data mapping logic"
    ],
    "next_best_actions": [
      "Correct transaction history display/data mapping",
      "Update CBS records if source data error found",
      "Escalate to IT team for module-level fix",
      "Reconcile and verify corrected history output"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Withdrawal Limit Issue",
    "investigation_steps": [
      "Check CBS/card management system for configured withdrawal limit",
      "Verify limit configuration against customer-requested/product-defined limit",
      "Review switch log for limit-related decline response code"
    ],
    "next_best_actions": [
      "Correct limit configuration in card management system",
      "Update CBS records",
      "Communicate limit correction to switch/network",
      "Verify limit change reflects correctly in subsequent transactions"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Daily Withdrawal Limit Incorrect",
    "investigation_steps": [
      "Check card management system for configured daily limit value",
      "Verify limit reset cycle and timestamp logic",
      "Cross-check CBS product/card variant default limit mapping"
    ],
    "next_best_actions": [
      "Correct daily limit configuration",
      "Update CBS and card management system records",
      "Verify limit reset cycle logic",
      "Confirm correction with test transaction if required"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Withdrawal Limit Not Updated",
    "investigation_steps": [
      "Check pending limit change request status in card management system",
      "Verify CBS workflow approval/processing log for the limit update request",
      "Cross-check sync between CBS and switch/card management system"
    ],
    "next_best_actions": [
      "Reprocess pending limit update request",
      "Escalate to IT/card management team for sync issue",
      "Update CBS records to reflect correct limit",
      "Verify limit update takes effect"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Rejecting Valid Card",
    "investigation_steps": [
      "Check switch response code for card rejection reason",
      "Verify card status (active/blocked/expired) in CBS",
      "Review EJ log for card reader interaction error",
      "Check BIN/card scheme routing configuration at the ATM"
    ],
    "next_best_actions": [
      "Correct card status in CBS if erroneously blocked",
      "Escalate to switch team for routing configuration fix",
      "Dispatch field engineer if card reader hardware fault confirmed",
      "Reissue card if physically defective"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Unable to Read Card",
    "investigation_steps": [
      "Check EJ log for card reader error code",
      "Verify card reader hardware diagnostic log",
      "Inspect card for physical/chip damage if returned by customer"
    ],
    "next_best_actions": [
      "Dispatch field engineer for card reader cleaning/repair",
      "Reissue card if card defect confirmed",
      "Flag ATM for hardware maintenance",
      "Update maintenance schedule for card reader"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Chip Card Read Error",
    "investigation_steps": [
      "Check EJ log for EMV chip read error code",
      "Verify card reader EMV module diagnostic log",
      "Cross-check card chip status/issuance batch records"
    ],
    "next_best_actions": [
      "Dispatch field engineer for EMV reader inspection",
      "Reissue card if chip defect confirmed",
      "Escalate to vendor for EMV module firmware check",
      "Flag ATM for EMV reader maintenance"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Magnetic Stripe Read Error",
    "investigation_steps": [
      "Check EJ log for magnetic stripe read error code",
      "Verify card reader magnetic head diagnostic/cleaning log",
      "Inspect card stripe condition if returned by customer"
    ],
    "next_best_actions": [
      "Dispatch field engineer for card reader head cleaning/repair",
      "Reissue card if stripe damage confirmed",
      "Flag ATM for hardware maintenance",
      "Escalate to vendor if recurring across multiple cards"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Card Authentication Failed",
    "investigation_steps": [
      "Check switch/HSM log for authentication response code",
      "Verify CBS/card management system card status and key validity",
      "Review EMV/PIN block translation logs at switch and HSM"
    ],
    "next_best_actions": [
      "Escalate to HSM/security team for key/translation issue",
      "Correct card authentication configuration if misconfigured",
      "Reissue card if authentication credential corrupted",
      "Verify resolution with test transaction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Language Selection Not Working",
    "investigation_steps": [
      "Check terminal application configuration log for language module",
      "Verify EJ log for language selection input response",
      "Review software version/patch log for the language module"
    ],
    "next_best_actions": [
      "Escalate to vendor/application team for software fix",
      "Reconfigure language module settings",
      "Schedule software patch deployment",
      "Verify fix with test transaction in affected language"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Accessibility Issue",
    "investigation_steps": [
      "Review ATM site accessibility audit report (ramp, height, signage)",
      "Check compliance status against accessibility guidelines for the location",
      "Verify any prior accessibility complaint history for the site"
    ],
    "next_best_actions": [
      "Escalate to facilities/infrastructure team for site modification",
      "Schedule accessibility compliance upgrade",
      "Update ATM site accessibility status in records",
      "Communicate interim alternate ATM location if available"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Wheelchair Access Not Available",
    "investigation_steps": [
      "Review ATM site infrastructure audit for ramp/access provision",
      "Check facility records for accessibility compliance status",
      "Verify site layout against accessibility design standards"
    ],
    "next_best_actions": [
      "Escalate to facilities/infrastructure team for ramp installation",
      "Schedule site modification for accessibility compliance",
      "Update site accessibility status in ATM records",
      "Communicate interim alternate accessible ATM location"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Withdrawal Delayed",
    "investigation_steps": [
      "Check EJ log for time lag between authorization and dispense",
      "Verify network/switch latency log for the transaction",
      "Review terminal hardware response time diagnostics"
    ],
    "next_best_actions": [
      "Escalate to network/switch team if latency-related",
      "Dispatch field engineer if hardware response delay confirmed",
      "Update terminal/network configuration to reduce latency",
      "Monitor transaction response time post-fix"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Deposit Reversal Delayed",
    "investigation_steps": [
      "Check CBS reversal entry status and processing timestamp",
      "Verify TAT compliance for deposit reversal workflow",
      "Cross-check reconciliation file for pending reversal entries"
    ],
    "next_best_actions": [
      "Expedite pending reversal processing",
      "Update CBS records",
      "Escalate to reconciliation team for delayed entries",
      "Report TAT breach for process review"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit Reversal Failed",
    "investigation_steps": [
      "Check CBS reversal request status and error/response code",
      "Verify EJ log for original deposit transaction details",
      "Cross-check vault/cash management reconciliation for the deposit"
    ],
    "next_best_actions": [
      "Reprocess failed reversal request",
      "Escalate to reconciliation team for manual correction",
      "Update CBS records",
      "Verify reversal reflects correctly in account"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Card Block Request After ATM Fraud",
    "investigation_steps": [
      "Verify card block request timestamp and status in CBS/card management system",
      "Check fraud monitoring system for transaction flags on the account",
      "Cross-check EJ log/CCTV for the fraudulent transaction details"
    ],
    "next_best_actions": [
      "Confirm card block is active and effective",
      "Reverse unauthorized transactions per dispute process",
      "Escalate to fraud investigation team",
      "Issue replacement card to customer"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Card Blocking Delay After ATM Incident",
    "investigation_steps": [
      "Check card management system log for block request processing timestamp versus request time",
      "Verify workflow/approval queue for delayed block processing",
      "Cross-check sync between CBS and switch/network blocklist propagation"
    ],
    "next_best_actions": [
      "Expedite pending card block request",
      "Escalate to IT/card management team for sync delay resolution",
      "Update CBS and network blocklist immediately",
      "Review process for reducing block propagation time"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Surveillance Footage Request",
    "investigation_steps": [
      "Check CCTV/DVR system for footage availability against requested date/time",
      "Verify footage retention period compliance for the ATM site",
      "Cross-check footage request approval/authorization records"
    ],
    "next_best_actions": [
      "Retrieve and extract requested footage from DVR system",
      "Forward footage to investigation/fraud/law enforcement team as authorized",
      "Update footage request log",
      "Escalate to security team if footage unavailable due to retention lapse"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Complaint Not Resolved",
    "investigation_steps": [
      "Review complaint case history and all prior investigation actions taken",
      "Check status of related CBS/switch/EJ investigation entries",
      "Verify reasons for delay or non-closure in the complaint tracking system"
    ],
    "next_best_actions": [
      "Reassign complaint for expedited resolution",
      "Complete pending investigation steps and close the case",
      "Update complaint tracking system with final resolution",
      "Escalate to next level if unresolved beyond defined cycle"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Located at Unsafe Premises",
    "investigation_steps": [
      "Review site security/safety audit report for the ATM location",
      "Check incident history log for the site",
      "Verify lighting, security guard, and surveillance status at the premises"
    ],
    "next_best_actions": [
      "Escalate to security/facilities team for site safety improvement",
      "Consider relocation of ATM if risk persists",
      "Arrange additional security measures (lighting, guard, alarm)",
      "Update ATM site risk assessment records"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Frequently Offline",
    "investigation_steps": [
      "Review ATM uptime/downtime monitoring report and connectivity logs",
      "Check network link status and historical outage pattern for the ATM",
      "Verify vendor SLA compliance for the site"
    ],
    "next_best_actions": [
      "Escalate to network operations team for link stability fix",
      "Arrange backup connectivity (secondary network link)",
      "Escalate to vendor for SLA breach review",
      "Monitor uptime post-resolution"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Cash Reconciliation Delay",
    "investigation_steps": [
      "Check vault/cash management reconciliation report processing status",
      "Verify cash-in/cash-out transaction logs against physical cash count",
      "Review reconciliation workflow for processing bottleneck"
    ],
    "next_best_actions": [
      "Expedite pending reconciliation processing",
      "Escalate to cash management team for backlog clearance",
      "Update CBS records post-reconciliation",
      "Review reconciliation process for efficiency improvement"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Deposit Envelope Not Processed",
    "investigation_steps": [
      "Check EJ log for envelope deposit acceptance confirmation",
      "Verify envelope processing/vault log for received envelope count",
      "Cross-check CBS for pending credit entry against envelope deposit"
    ],
    "next_best_actions": [
      "Process pending envelope deposit credit after vault verification",
      "Escalate to cash management team for processing backlog",
      "Update CBS records",
      "Reconcile envelope count with vault report"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Envelope Deposit Missing",
    "investigation_steps": [
      "Check EJ log for envelope deposit transaction record",
      "Verify vault/cash management log for envelope receipt count",
      "Cross-check CBS for any related credit/hold entry"
    ],
    "next_best_actions": [
      "Investigate discrepancy with vault custodian/cash management team",
      "Process credit if envelope verified as received",
      "Escalate to vendor/cash-in-transit team if envelope not traced",
      "Update CBS records post-investigation"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Cash Counter Error",
    "investigation_steps": [
      "Check cash counter/sensor calibration log at the ATM",
      "Verify EJ log for note count discrepancy versus cassette load",
      "Cross-check vault reconciliation report for variance"
    ],
    "next_best_actions": [
      "Recalibrate cash counter/sensor hardware",
      "Reconcile cash variance with vault management report",
      "Escalate to vendor for hardware inspection",
      "Update cassette loading records post-correction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit Machine Out of Service",
    "investigation_steps": [
      "Check CDM monitoring dashboard for terminal status code",
      "Verify last heartbeat/connectivity log for the CDM",
      "Review maintenance ticket history and vendor field service log"
    ],
    "next_best_actions": [
      "Escalate to field service/vendor team for restoration",
      "Mark CDM as out-of-service in locator/monitoring system",
      "Schedule preventive maintenance",
      "Update CDM status in monitoring system"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit Machine Offline",
    "investigation_steps": [
      "Check CDM-to-host network connectivity log",
      "Verify network latency/timeout logs at the site",
      "Review switch/host connectivity status for the CDM"
    ],
    "next_best_actions": [
      "Escalate to network operations team for connectivity restoration",
      "Reroute CDM to backup network link if available",
      "Monitor connectivity post-fix",
      "Update CDM status in monitoring dashboard"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit Machine Not Accepting Notes",
    "investigation_steps": [
      "Check note validator/cash acceptor hardware fault log",
      "Review EJ log for repeated note rejection error codes",
      "Verify validator calibration/cleaning log"
    ],
    "next_best_actions": [
      "Dispatch field engineer for note validator inspection/calibration",
      "Take CDM offline until rectified",
      "Flag for vendor hardware maintenance",
      "Update CDM status in monitoring dashboard"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit Machine Accepted Cash but Failed Transaction",
    "investigation_steps": [
      "Check EJ log for note acceptance confirmation versus transaction completion status",
      "Verify CBS for any provisional hold/credit entry",
      "Cross-check vault reconciliation report for accepted cash count"
    ],
    "next_best_actions": [
      "Credit account based on verified cash-in count from vault reconciliation",
      "Update CBS records to close failed transaction",
      "Escalate to vendor if hardware-software sync issue identified",
      "Reconcile cash variance with vault report"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit Machine Accepted Cash but No Receipt",
    "investigation_steps": [
      "Check EJ log for printer command status against confirmed cash acceptance",
      "Verify printer hardware/paper-out fault log",
      "Confirm transaction completion status in CBS independent of receipt"
    ],
    "next_best_actions": [
      "Issue duplicate transaction confirmation/receipt",
      "Dispatch field engineer for printer fault rectification",
      "Reconcile transaction with CBS records",
      "Flag CDM for printer maintenance"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit Machine Accepted Cash but Amount Incorrect",
    "investigation_steps": [
      "Check EJ log for note count and denomination accepted versus credited amount",
      "Verify note validator denomination recognition log",
      "Cross-check CBS credited amount against vault reconciliation report"
    ],
    "next_best_actions": [
      "Correct credited amount based on verified vault reconciliation",
      "Update CBS records",
      "Escalate to vendor for note validator calibration check",
      "Reconcile cash variance with vault report"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Software Error",
    "investigation_steps": [
      "Check terminal application error/crash log",
      "Verify software version and patch deployment history for the ATM",
      "Review vendor incident log for known software defects"
    ],
    "next_best_actions": [
      "Escalate to vendor/application support team for patch deployment",
      "Restart/reset terminal application",
      "Reverse any transaction impacted by the software error",
      "Schedule software update across affected ATM fleet"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Restart During Transaction",
    "investigation_steps": [
      "Check EJ log for transaction status prior to restart event",
      "Verify terminal system/application crash log for restart trigger",
      "Cross-check CBS transaction status against terminal log"
    ],
    "next_best_actions": [
      "Reverse any incomplete debit caused by the restart",
      "Escalate to vendor for root cause of unexpected restart",
      "Update CBS records post-reconciliation",
      "Flag ATM for software/hardware diagnostic"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Withdrawal SMS Not Received",
    "investigation_steps": [
      "Check SMS gateway delivery log for the transaction alert",
      "Verify registered mobile number and alert subscription status in CBS",
      "Review CBS alert trigger log for the transaction"
    ],
    "next_best_actions": [
      "Resend transaction alert SMS",
      "Correct mobile number/subscription mapping if found incorrect",
      "Escalate to SMS gateway vendor if delivery failure confirmed",
      "Verify alert delivery post-correction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Deposit SMS Not Received",
    "investigation_steps": [
      "Check SMS gateway delivery log for the deposit alert",
      "Verify registered mobile number and alert subscription status in CBS",
      "Review CBS alert trigger log for the deposit transaction"
    ],
    "next_best_actions": [
      "Resend transaction alert SMS",
      "Correct mobile number/subscription mapping if found incorrect",
      "Escalate to SMS gateway vendor if delivery failure confirmed",
      "Verify alert delivery post-correction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM OTP Not Received",
    "investigation_steps": [
      "Check OTP gateway delivery log for the transaction request",
      "Verify registered mobile number mapping in CBS",
      "Review OTP generation/trigger log at switch/CBS level"
    ],
    "next_best_actions": [
      "Resend OTP request",
      "Correct mobile number mapping if found incorrect",
      "Escalate to OTP/SMS gateway vendor if delivery failure confirmed",
      "Verify OTP delivery post-correction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cash Withdrawal Successful but Balance Incorrect",
    "investigation_steps": [
      "Check CBS ledger entry against actual debit amount for the transaction",
      "Verify EJ log for dispensed amount versus CBS posted amount",
      "Cross-check for any concurrent transaction affecting balance computation"
    ],
    "next_best_actions": [
      "Correct CBS balance entry post-verification",
      "Reconcile with settlement file",
      "Escalate to core banking team if systemic posting error found",
      "Verify corrected balance reflects accurately"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Balance Not Updated After Withdrawal",
    "investigation_steps": [
      "Check CBS posting log for the withdrawal transaction",
      "Verify batch/real-time posting job status for the account",
      "Cross-check switch settlement file against CBS ledger"
    ],
    "next_best_actions": [
      "Manually post the pending debit entry to update balance",
      "Escalate to core banking/batch processing team if job failure identified",
      "Reconcile with settlement file",
      "Verify balance update reflects correctly"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Balance Not Updated After Deposit",
    "investigation_steps": [
      "Check CBS posting log for the deposit transaction",
      "Verify batch/real-time posting job status for the account",
      "Cross-check vault/cash management reconciliation against CBS ledger"
    ],
    "next_best_actions": [
      "Manually post the pending credit entry to update balance",
      "Escalate to core banking/batch processing team if job failure identified",
      "Reconcile with vault/settlement report",
      "Verify balance update reflects correctly"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Cardless Withdrawal Failed",
    "investigation_steps": [
      "Check CBS/mobile banking log for cardless withdrawal request status",
      "Verify OTP/authentication token validation log for the request",
      "Review switch/EJ log for terminal-side processing error"
    ],
    "next_best_actions": [
      "Reverse any debit/hold without successful dispense",
      "Retry cardless withdrawal request processing",
      "Escalate to mobile banking/switch team if token validation error found",
      "Update CBS records"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cardless Withdrawal OTP Expired",
    "investigation_steps": [
      "Check OTP generation and expiry timestamp log against transaction attempt time",
      "Verify OTP validity configuration in mobile banking/switch system",
      "Review delivery log for OTP transmission delay"
    ],
    "next_best_actions": [
      "Regenerate OTP for the customer to retry transaction",
      "Adjust OTP validity window if configuration found too short",
      "Escalate to gateway team if delivery delay caused expiry",
      "Verify resolution with test transaction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "Cardless Withdrawal Pending",
    "investigation_steps": [
      "Check switch/mobile banking queue status for the cardless transaction",
      "Verify CBS hold/pending entry against the transaction reference",
      "Review EJ log for terminal response status"
    ],
    "next_best_actions": [
      "Auto-reverse pending transaction post TAT if undispensed",
      "Update CBS to release hold",
      "Reconcile with settlement file",
      "Escalate unresolved pending entries to switch/network team"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM QR Withdrawal Failed",
    "investigation_steps": [
      "Check QR transaction log in switch/mobile banking system for request status",
      "Verify QR code generation and scan validation log at the ATM",
      "Review CBS for any provisional debit/hold entry"
    ],
    "next_best_actions": [
      "Reverse any debit without successful dispense",
      "Retry QR withdrawal request processing",
      "Escalate to QR service provider/switch team for validation error",
      "Update CBS records"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM QR Code Not Working",
    "investigation_steps": [
      "Check QR code generation/display module log at the terminal",
      "Verify QR scanner hardware/software diagnostic log",
      "Review software version for QR module compatibility issues"
    ],
    "next_best_actions": [
      "Escalate to vendor/application team for QR module fix",
      "Dispatch field engineer if scanner hardware fault confirmed",
      "Schedule software patch for QR module",
      "Verify fix with test QR transaction"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Location Not Available in App",
    "investigation_steps": [
      "Check ATM master data sync log between core system and mobile/internet banking app",
      "Verify ATM geolocation and status data feed configuration",
      "Review API/data integration log for the ATM locator service"
    ],
    "next_best_actions": [
      "Update ATM master data and geolocation records",
      "Escalate to IT/digital banking team for data sync fix",
      "Republish corrected ATM locator feed",
      "Verify ATM appears correctly in app post-update"
    ]
  },
  {
    "major_issue": "ATM",
    "sub_issue": "ATM Cash Forecast Incorrect",
    "investigation_steps": [
      "Review cash forecast model parameters and historical withdrawal pattern data for the ATM",
      "Verify cash replenishment log against forecast-predicted requirement",
      "Check data feed/integration log between transaction history and forecasting system"
    ],
    "next_best_actions": [
      "Recalibrate cash forecast model parameters",
      "Escalate to cash management/analytics team for model correction",
      "Adjust replenishment schedule based on corrected forecast",
      "Monitor forecast accuracy post-correction"
    ]
  }
],
[
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Internet Banking Registration Failed",
    "investigation_steps": [
      "Verify customer account status in CBS (active/dormant/closed)",
      "Check internet banking registration request logs in digital banking platform",
      "Review error codes generated during registration attempt",
      "Verify KYC and account eligibility for internet banking registration",
      "Check if registered mobile number in CBS matches customer's input",
      "Verify OTP delivery logs during registration",
      "Review digital banking platform API logs for registration failure"
    ],
    "next_best_actions": [
      "Resolve account eligibility or KYC issues in CBS",
      "Update registered mobile number in CBS if mismatch identified",
      "Manually trigger registration in digital banking platform if system error confirmed",
      "Escalate to digital banking or IT team for platform-level failure",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Login Failed",
    "investigation_steps": [
      "Retrieve login failure logs from digital banking platform",
      "Check error codes returned during login attempt",
      "Verify user ID and account status in digital banking platform",
      "Check if account is locked or suspended in digital banking platform",
      "Review failed login attempt count and lockout policy",
      "Verify CBS account status linked to internet banking profile"
    ],
    "next_best_actions": [
      "Unlock user account in digital banking platform if locked due to failed attempts",
      "Reset credentials if system error caused login failure",
      "Escalate to digital banking or IT team if platform-level failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Invalid Username or Password",
    "investigation_steps": [
      "Verify user ID existence in digital banking platform",
      "Check failed login attempt logs and error codes",
      "Verify if user ID or password was recently changed in platform",
      "Review lockout status of user account",
      "Check if any system migration caused credential invalidation"
    ],
    "next_best_actions": [
      "Initiate password reset process for customer",
      "Unlock user account if locked due to invalid attempts",
      "Escalate to digital banking team if credential system migration issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Username Not Recognized",
    "investigation_steps": [
      "Verify user ID registration status in digital banking platform",
      "Check if internet banking registration was completed successfully",
      "Review CBS account linkage to internet banking profile",
      "Check if user ID was deactivated or removed from platform",
      "Verify if system migration caused user ID data loss"
    ],
    "next_best_actions": [
      "Re-register internet banking if registration was incomplete",
      "Restore user ID in digital banking platform if system error identified",
      "Escalate to digital banking or IT team for platform-level data issue",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Password Reset Failed",
    "investigation_steps": [
      "Retrieve password reset request logs from digital banking platform",
      "Check error codes returned during password reset attempt",
      "Verify registered mobile number and email ID in CBS for OTP delivery",
      "Review OTP delivery logs during password reset",
      "Check if password reset link was generated and delivered",
      "Verify if account is locked or inactive in digital banking platform"
    ],
    "next_best_actions": [
      "Manually trigger password reset in digital banking platform",
      "Update registered mobile number or email in CBS if delivery failure identified",
      "Unlock account in digital banking platform if locked",
      "Escalate to digital banking or IT team if platform failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Password Reset Link Expired",
    "investigation_steps": [
      "Verify password reset link generation timestamp in digital banking platform logs",
      "Check configured link expiry duration in platform settings",
      "Verify if customer attempted link usage after expiry window",
      "Review if multiple reset links were generated causing earlier link invalidation"
    ],
    "next_best_actions": [
      "Generate a fresh password reset link and deliver to customer",
      "Escalate to digital banking team if link expiry configuration is erroneous",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Forgot Password Issue",
    "investigation_steps": [
      "Retrieve forgot password request logs from digital banking platform",
      "Check error codes during forgot password workflow",
      "Verify registered mobile number and email ID in CBS for OTP/link delivery",
      "Review OTP and reset link delivery logs",
      "Verify account status in digital banking platform"
    ],
    "next_best_actions": [
      "Manually initiate password reset in digital banking platform",
      "Update registered mobile number or email in CBS if delivery failure identified",
      "Escalate to digital banking or IT team if platform failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Account Locked",
    "investigation_steps": [
      "Verify account lock status and reason in digital banking platform",
      "Check failed login attempt count triggering lockout",
      "Verify if lock was manually applied by operations/security team",
      "Check if fraud or suspicious activity trigger caused auto-lock",
      "Review security alert logs associated with account lock"
    ],
    "next_best_actions": [
      "Unlock account in digital banking platform after identity verification",
      "Initiate password reset post unlock",
      "Escalate to security team if fraud-triggered lock",
      "Update fraud management system if security threat identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "User ID Locked",
    "investigation_steps": [
      "Verify user ID lock status and reason in digital banking platform",
      "Check failed authentication attempt count triggering lockout",
      "Verify if lock was manually applied by operations or security team",
      "Review security alert logs associated with user ID lock",
      "Check if fraud rule triggered auto-lock"
    ],
    "next_best_actions": [
      "Unlock user ID in digital banking platform after identity verification",
      "Initiate credential reset post unlock",
      "Escalate to security team if fraud-triggered lock confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Security Questions Not Accepted",
    "investigation_steps": [
      "Retrieve security question verification logs from digital banking platform",
      "Check error codes returned during security question verification",
      "Verify security questions and answers stored in digital banking platform",
      "Check attempt count for security question verification failure",
      "Verify if security question data was affected by system migration"
    ],
    "next_best_actions": [
      "Reset security questions in digital banking platform after identity verification",
      "Unlock account if locked due to failed security question attempts",
      "Escalate to digital banking or IT team if data migration issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Two-Factor Authentication Failed",
    "investigation_steps": [
      "Retrieve 2FA failure logs from digital banking platform",
      "Check 2FA method configured: OTP, TOTP, hardware token",
      "Verify OTP delivery logs and SMS gateway records",
      "Verify registered mobile number in CBS for OTP receipt",
      "Check TOTP synchronization if authenticator app is used",
      "Review 2FA service availability logs"
    ],
    "next_best_actions": [
      "Update registered mobile number in CBS if OTP delivery failure identified",
      "Reset TOTP enrollment if authenticator app sync issue identified",
      "Escalate to digital banking or IT team if 2FA service failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "OTP Not Received",
    "investigation_steps": [
      "Verify OTP generation logs in digital banking platform",
      "Check SMS gateway delivery logs for OTP dispatch",
      "Verify registered mobile number in CBS",
      "Check if mobile number is DND registered",
      "Review telecom carrier routing for registered number",
      "Verify email OTP delivery if alternate OTP channel used"
    ],
    "next_best_actions": [
      "Update registered mobile number in CBS if incorrect",
      "Escalate to SMS gateway provider if delivery failure confirmed",
      "Check and resolve DND registration if applicable",
      "Escalate to digital banking team for OTP service review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "OTP Expired",
    "investigation_steps": [
      "Verify OTP generation timestamp in digital banking platform logs",
      "Check configured OTP validity duration in platform settings",
      "Verify if customer attempted OTP entry after expiry window",
      "Check if OTP delivery was delayed causing expiry by time of receipt"
    ],
    "next_best_actions": [
      "Trigger fresh OTP generation for customer",
      "Escalate to SMS gateway provider if OTP delivery delay identified",
      "Escalate to digital banking team if OTP expiry configuration is erroneous",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "OTP Verification Failed",
    "investigation_steps": [
      "Retrieve OTP verification failure logs from digital banking platform",
      "Check error codes returned during OTP verification",
      "Verify OTP attempt count for the session",
      "Check if OTP entered was for a different session or transaction",
      "Verify OTP generation and delivery timestamp for timing issues"
    ],
    "next_best_actions": [
      "Trigger fresh OTP for customer",
      "Unlock OTP verification if max attempt lockout triggered",
      "Escalate to digital banking or IT team if OTP verification system failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Device Registration Failed",
    "investigation_steps": [
      "Retrieve device registration request logs from digital banking platform",
      "Check error codes returned during device registration attempt",
      "Verify OTP delivery for device registration authentication",
      "Review device fingerprinting and registration service logs",
      "Check if maximum registered device limit is reached for customer profile",
      "Verify account status in digital banking platform"
    ],
    "next_best_actions": [
      "Retry device registration after resolving OTP or authentication issue",
      "Remove old/unused device registrations if limit reached",
      "Escalate to digital banking or IT team if device registration service failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Browser Compatibility Issue",
    "investigation_steps": [
      "Identify browser name, version, and OS reported by customer",
      "Check digital banking platform's supported browser and version matrix",
      "Review platform release notes for known browser compatibility issues",
      "Check frontend error logs if browser error details are available",
      "Verify if browser security settings or extensions are blocking portal functions"
    ],
    "next_best_actions": [
      "Escalate to digital banking IT team if browser compatibility bug confirmed",
      "Update supported browser matrix if new version incompatibility identified",
      "Raise change request for browser compatibility fix",
      "Update CRM with investigation findings"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Net Banking Portal Not Accessible",
    "investigation_steps": [
      "Verify digital banking portal uptime and availability via monitoring tools",
      "Check web server and application server logs for downtime or errors",
      "Verify DNS resolution and CDN status for the portal URL",
      "Check for any ongoing maintenance window or deployment activity",
      "Review network infrastructure logs for access issues"
    ],
    "next_best_actions": [
      "Escalate to IT infrastructure team for portal restoration",
      "Engage CDN/DNS provider if network-level accessibility issue confirmed",
      "Communicate maintenance or downtime to customer service team",
      "Update CRM with portal restoration status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Website Down",
    "investigation_steps": [
      "Verify website uptime via monitoring tools and health check endpoints",
      "Check web server and application server logs for crash or error",
      "Review infrastructure and network monitoring dashboards",
      "Check for any recent deployment or configuration change causing outage",
      "Verify database connectivity from web application servers"
    ],
    "next_best_actions": [
      "Escalate to IT infrastructure and application team immediately for restoration",
      "Initiate disaster recovery or failover procedure if applicable",
      "Roll back recent deployment if change-induced outage confirmed",
      "Update CRM and internal communication channels with outage status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Server Unavailable",
    "investigation_steps": [
      "Verify application server and database server status via monitoring tools",
      "Check server health metrics: CPU, memory, disk utilization",
      "Review server error logs for crash, overload, or service failure",
      "Check for any scheduled maintenance or unplanned outage",
      "Verify network connectivity between web and application servers"
    ],
    "next_best_actions": [
      "Escalate to IT infrastructure team for immediate server restoration",
      "Initiate failover to standby server if applicable",
      "Review and address root cause: overload, crash, or network failure",
      "Update CRM with server restoration status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Session Timed Out",
    "investigation_steps": [
      "Verify session timeout configuration in digital banking platform",
      "Review session management logs for premature timeout events",
      "Check if customer's transaction was in progress during timeout",
      "Verify if any amount was debited due to incomplete transaction during session timeout",
      "Check network latency or inactivity triggers for timeout"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited during incomplete transaction due to session timeout",
      "Escalate to digital banking team if session timeout is premature/misconfigured",
      "Review and adjust session timeout parameters if operationally appropriate",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Unexpected Logout",
    "investigation_steps": [
      "Retrieve session logs from digital banking platform for unexpected logout event",
      "Check if concurrent login from another device triggered logout",
      "Review security policy for single-session enforcement causing logout",
      "Check for platform errors or exceptions triggering session termination",
      "Verify if any amount was debited due to incomplete transaction during unexpected logout"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited during incomplete transaction",
      "Escalate to digital banking or IT team if platform error caused unexpected logout",
      "Review concurrent session policy if multiple login conflict identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Dashboard Not Loading",
    "investigation_steps": [
      "Retrieve dashboard load failure logs from digital banking platform",
      "Check error codes or exceptions during dashboard rendering",
      "Verify CBS API connectivity for account data fetch",
      "Check if dashboard failure is user-specific or affecting multiple users",
      "Review frontend application logs and browser console errors",
      "Verify if recent platform deployment caused dashboard issue"
    ],
    "next_best_actions": [
      "Escalate to digital banking IT team if platform or API failure identified",
      "Roll back recent deployment if change-induced issue confirmed",
      "Escalate to CBS team if CBS API connectivity issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Transaction History Not Loading",
    "investigation_steps": [
      "Retrieve transaction history load failure logs from digital banking platform",
      "Check error codes or exceptions during transaction history fetch",
      "Verify CBS API connectivity for transaction data retrieval",
      "Check if issue is user-specific or affecting multiple users",
      "Verify date range and filters applied for transaction history fetch",
      "Review backend API and database query performance logs"
    ],
    "next_best_actions": [
      "Escalate to digital banking IT team if platform or API failure identified",
      "Escalate to CBS team if CBS data fetch failure confirmed",
      "Optimize backend query if performance issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Transaction History Missing",
    "investigation_steps": [
      "Verify transaction history in CBS for the disputed period",
      "Check if transactions exist in CBS but are missing in digital banking platform display",
      "Review CBS-to-digital banking data synchronization logs",
      "Verify if date range or filter is excluding relevant transactions",
      "Check if data migration or platform upgrade caused history gap"
    ],
    "next_best_actions": [
      "Trigger CBS-to-digital banking data sync if sync failure identified",
      "Escalate to digital banking IT team for data reconciliation",
      "Provide account statement from CBS as interim resolution",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Statement Download Failed",
    "investigation_steps": [
      "Retrieve statement download failure logs from digital banking platform",
      "Check error codes returned during download attempt",
      "Verify CBS API connectivity for statement data fetch",
      "Check if statement generation service is operational",
      "Verify selected date range and account for statement download",
      "Check PDF/statement generation service logs"
    ],
    "next_best_actions": [
      "Retry statement generation from CBS",
      "Escalate to digital banking IT team if statement generation service failure confirmed",
      "Provide statement via alternate channel (email/branch) as interim resolution",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Statement Not Available",
    "investigation_steps": [
      "Verify availability of account statement in CBS for the requested period",
      "Check if account was active during the requested statement period",
      "Review digital banking platform statement availability configuration",
      "Verify if statement archival period covers the requested date range",
      "Check CBS data retention policy for transaction history"
    ],
    "next_best_actions": [
      "Generate and provide statement from CBS for the requested period",
      "Escalate to CBS team if data gap identified for the period",
      "Escalate to digital banking team if platform configuration limits statement availability",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "E-Statement Not Received",
    "investigation_steps": [
      "Verify e-statement generation and dispatch logs in digital banking platform",
      "Check email delivery logs for e-statement dispatch",
      "Verify registered email ID in CBS",
      "Check if email was delivered to spam or junk folder",
      "Review e-statement dispatch schedule and confirm if dispatch was triggered",
      "Check email service provider delivery status"
    ],
    "next_best_actions": [
      "Re-send e-statement to verified email ID",
      "Update registered email ID in CBS if incorrect",
      "Escalate to email service provider if delivery failure confirmed",
      "Provide statement via alternate channel as interim resolution",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Account Balance Not Updated",
    "investigation_steps": [
      "Verify current account balance in CBS",
      "Check CBS-to-digital banking balance synchronization logs",
      "Identify pending transactions that may affect balance update",
      "Review balance refresh/sync frequency configuration in digital banking platform",
      "Check if any system delay or outage affected balance sync"
    ],
    "next_best_actions": [
      "Trigger manual balance refresh/sync in digital banking platform",
      "Escalate to digital banking IT team if sync failure confirmed",
      "Escalate to CBS team if balance discrepancy exists in CBS itself",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Incorrect Balance Displayed",
    "investigation_steps": [
      "Verify actual account balance in CBS",
      "Compare CBS balance against balance displayed in digital banking platform",
      "Check for any lien, hold, or uncleared instruments affecting available balance",
      "Review CBS-to-digital banking balance data mapping",
      "Verify if balance display is showing ledger balance vs available balance incorrectly"
    ],
    "next_best_actions": [
      "Correct balance display mapping in digital banking platform if data mapping error identified",
      "Trigger manual balance sync from CBS",
      "Escalate to digital banking IT team if platform data mapping issue confirmed",
      "Release any erroneous lien or hold in CBS if applicable",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Fund Transfer Failed",
    "investigation_steps": [
      "Retrieve fund transfer failure logs from digital banking platform and switch",
      "Check error codes returned during transfer attempt",
      "Verify account balance in CBS at time of transfer",
      "Verify beneficiary account details in digital banking platform",
      "Check payment network (NEFT/RTGS/IMPS) processing logs",
      "Verify transfer limits in digital banking platform",
      "Check if amount was debited despite transfer failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but transfer failed",
      "Verify and correct beneficiary details if data error identified",
      "Escalate to payment network if network-level failure confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Fund Transfer Pending",
    "investigation_steps": [
      "Retrieve fund transfer status from CBS and payment network",
      "Verify debit posting in CBS",
      "Check payment network processing status (NEFT/RTGS/IMPS/batch cycle)",
      "Verify beneficiary bank credit status",
      "Review reconciliation records for pending transfer"
    ],
    "next_best_actions": [
      "Follow up with payment network for transfer credit confirmation",
      "Escalate to NPCI/RBI if payment network settlement is delayed",
      "Credit beneficiary account if settlement confirmed but posting pending",
      "Initiate reversal if transfer cannot be completed",
      "Update CRM with transfer status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Fund Transfer Timed Out",
    "investigation_steps": [
      "Retrieve transfer timeout logs from digital banking platform and switch",
      "Verify if debit was posted in CBS despite timeout",
      "Check payment network status for the timed-out transaction",
      "Verify reconciliation records for the transaction",
      "Review network latency or API timeout configuration"
    ],
    "next_best_actions": [
      "Initiate reversal in CBS if debit posted but transfer did not complete",
      "Verify with payment network if transfer was processed despite timeout",
      "Escalate to digital banking IT team for timeout configuration review",
      "Reconcile transaction with payment network",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Amount Debited but Beneficiary Not Credited",
    "investigation_steps": [
      "Verify debit posting in CBS",
      "Check payment network (NEFT/RTGS/IMPS) settlement records",
      "Verify beneficiary bank credit status via payment network",
      "Review reconciliation records for the transaction date",
      "Check if transaction is in pending or failed status at payment network"
    ],
    "next_best_actions": [
      "Initiate payment network trace request for the transaction",
      "Escalate to NPCI/beneficiary bank for credit confirmation",
      "Initiate reversal if payment network confirms non-credit",
      "Reconcile settlement with payment network",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Amount Debited but Transfer Failed",
    "investigation_steps": [
      "Verify debit posting in CBS",
      "Check switch and payment network logs for transfer failure reason",
      "Verify if auto-reversal was triggered by payment network or switch",
      "Review reconciliation records for pending reversal",
      "Check payment network settlement status"
    ],
    "next_best_actions": [
      "Initiate manual reversal in CBS if auto-reversal not triggered",
      "Escalate to switch/IT team if auto-reversal mechanism failed",
      "Reconcile transaction with payment network",
      "Credit customer account upon confirmed reversal",
      "Update CRM with reversal details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Duplicate Fund Transfer",
    "investigation_steps": [
      "Retrieve all fund transfer logs for the disputed date from CBS",
      "Verify if two separate debit entries exist for the same transfer",
      "Check switch and payment network logs for duplicate transaction processing",
      "Verify transaction reference numbers for both transfers",
      "Review reconciliation records for duplicate settlement"
    ],
    "next_best_actions": [
      "Initiate reversal of duplicate transfer in CBS",
      "Recall duplicate credit from beneficiary bank via payment network",
      "Escalate to switch/IT team if system-generated duplicate identified",
      "Reconcile with payment network",
      "Update CRM with reversal details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Transfer Reversed Unexpectedly",
    "investigation_steps": [
      "Retrieve transfer reversal logs from CBS and payment network",
      "Check reversal reason code from payment network",
      "Verify if beneficiary account details were incorrect causing return",
      "Check NPCI/payment network return transaction records",
      "Verify if reversal was system-triggered or manually initiated",
      "Review reconciliation records for the reversal"
    ],
    "next_best_actions": [
      "Credit reversed amount back to customer account in CBS",
      "Verify and correct beneficiary details and re-initiate transfer if required",
      "Escalate to payment network for return reason clarification",
      "Update CRM with reversal reason and corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Transfer Scheduled but Not Executed",
    "investigation_steps": [
      "Retrieve scheduled transfer details from digital banking platform",
      "Check scheduled transfer processing logs for execution failure",
      "Verify account balance on scheduled execution date in CBS",
      "Review digital banking scheduler service logs for the scheduled date",
      "Check if system downtime or maintenance window caused execution failure"
    ],
    "next_best_actions": [
      "Manually execute pending transfer if balance and details are valid",
      "Escalate to digital banking IT team if scheduler failure confirmed",
      "Reschedule transfer if execution window has passed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Standing Instruction Failed",
    "investigation_steps": [
      "Retrieve standing instruction details from CBS",
      "Verify account balance at scheduled execution time in CBS",
      "Check CBS standing instruction processing logs for error codes",
      "Verify if standing instruction is still active and correctly configured in CBS",
      "Review payment network processing logs for standing instruction transfer"
    ],
    "next_best_actions": [
      "Retry standing instruction execution if balance/status issue resolved",
      "Update standing instruction parameters in CBS if misconfigured",
      "Escalate to CBS team if system processing failure identified",
      "Notify relevant parties of failed standing instruction",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Scheduled Payment Failed",
    "investigation_steps": [
      "Retrieve scheduled payment details from digital banking platform",
      "Check scheduled payment processing logs for failure reason",
      "Verify account balance on scheduled payment date in CBS",
      "Review digital banking scheduler and payment gateway logs",
      "Check if payment failure was due to card/account status issue"
    ],
    "next_best_actions": [
      "Manually execute failed payment if balance and details are valid",
      "Escalate to digital banking IT team if scheduler or payment gateway failure confirmed",
      "Reschedule payment if execution window has passed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Recurring Transfer Failed",
    "investigation_steps": [
      "Retrieve recurring transfer/mandate details from CBS or NACH system",
      "Verify account balance on execution date in CBS",
      "Check NACH/e-mandate processing logs for failure reason",
      "Verify mandate registration and validity in NPCI NACH system",
      "Review CBS recurring transfer processing logs for error codes"
    ],
    "next_best_actions": [
      "Retry recurring transfer if balance/status issue resolved",
      "Re-register NACH mandate if mandate issue identified",
      "Escalate to NPCI NACH team if systemic failure confirmed",
      "Notify destination party of recurring transfer failure",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Beneficiary Addition Failed",
    "investigation_steps": [
      "Retrieve beneficiary addition request logs from digital banking platform",
      "Check error codes returned during beneficiary addition attempt",
      "Verify beneficiary account details: account number, IFSC, name",
      "Check IFSC validation and beneficiary bank verification status",
      "Verify if beneficiary addition limit is reached on customer profile",
      "Review OTP authentication logs for beneficiary addition"
    ],
    "next_best_actions": [
      "Verify and correct beneficiary details if data error identified",
      "Remove inactive beneficiaries if limit exceeded",
      "Escalate to digital banking IT team if platform failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Beneficiary Activation Pending",
    "investigation_steps": [
      "Verify beneficiary addition status in digital banking platform",
      "Check beneficiary activation cooling-off period configuration",
      "Review OTP or 2FA authentication logs for beneficiary addition",
      "Verify if activation is pending due to system delay or error",
      "Check activation queue for pending beneficiary records"
    ],
    "next_best_actions": [
      "Manually activate beneficiary in digital banking platform if cooling-off period has elapsed",
      "Escalate to digital banking IT team if system delay causing activation failure",
      "Update CRM with activation status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Beneficiary Verification Failed",
    "investigation_steps": [
      "Retrieve beneficiary verification logs from digital banking platform",
      "Check error codes during beneficiary verification",
      "Verify beneficiary account number and IFSC against payment network records",
      "Check penny drop or account validation service logs if used",
      "Verify if beneficiary bank IFSC is valid and active in NPCI database"
    ],
    "next_best_actions": [
      "Verify and correct beneficiary IFSC and account details",
      "Escalate to digital banking IT team if penny drop/verification service failure confirmed",
      "Escalate to NPCI if IFSC validation failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Beneficiary Removal Failed",
    "investigation_steps": [
      "Retrieve beneficiary removal request logs from digital banking platform",
      "Check error codes returned during removal attempt",
      "Verify beneficiary status in digital banking platform",
      "Check if active standing instructions or scheduled payments are linked to beneficiary",
      "Review platform processing queue for pending removal requests"
    ],
    "next_best_actions": [
      "Cancel or reassign linked standing instructions before removal",
      "Manually remove beneficiary in digital banking platform if system error confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Beneficiary Modification Failed",
    "investigation_steps": [
      "Retrieve beneficiary modification request logs from digital banking platform",
      "Check error codes returned during modification attempt",
      "Verify OTP authentication logs for modification request",
      "Check if modification is restricted due to active transactions linked to beneficiary",
      "Review platform processing queue for pending modification requests"
    ],
    "next_best_actions": [
      "Re-authenticate and retry beneficiary modification",
      "Manually update beneficiary details in digital banking platform if system error confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Incorrect Beneficiary Credited",
    "investigation_steps": [
      "Retrieve fund transfer details from CBS and payment network",
      "Verify beneficiary account number and IFSC used for transfer",
      "Confirm if transfer was sent to incorrect beneficiary due to data entry or system error",
      "Check digital banking platform beneficiary mapping for the customer",
      "Verify receiving bank and account details via payment network"
    ],
    "next_best_actions": [
      "Initiate payment recall request via payment network (NEFT/RTGS/IMPS return)",
      "Coordinate with beneficiary bank for credit reversal",
      "Escalate to NPCI if payment network-level recall required",
      "Update beneficiary details in digital banking platform if mapping error identified",
      "Update CRM with recall request details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Transfer Limit Exceeded Incorrectly",
    "investigation_steps": [
      "Verify transfer limit configuration on customer profile in digital banking platform",
      "Check cumulative transfer amount for the day in CBS",
      "Review switch and digital banking logs for limit breach error",
      "Verify if limit was recently updated or reset in digital banking platform",
      "Check RBI/NPCI prescribed limits for the transfer channel and account type"
    ],
    "next_best_actions": [
      "Correct transfer limit configuration in digital banking platform if misconfigured",
      "Reset daily limit counter if system error caused incorrect count",
      "Escalate to digital banking IT team for limit configuration review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Daily Transfer Limit Not Updated",
    "investigation_steps": [
      "Verify transfer limit update request in CRM and digital banking platform",
      "Check digital banking platform for current limit configuration",
      "Review platform update logs for limit update failure or pending status",
      "Verify if update request was within regulatory prescribed bounds",
      "Check system queue for pending limit update requests"
    ],
    "next_best_actions": [
      "Manually update transfer limit in digital banking platform",
      "Escalate to digital banking IT team if system update failure confirmed",
      "Verify regulatory compliance of requested limit",
      "Notify customer via SMS/email upon successful update",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "NEFT Transfer Failed",
    "investigation_steps": [
      "Retrieve NEFT transfer failure logs from CBS and NPCI NEFT system",
      "Check error/return codes from NPCI NEFT processing",
      "Verify debit posting in CBS",
      "Check NEFT batch processing status for the transaction date and time",
      "Verify beneficiary account number and IFSC",
      "Review reconciliation records for NEFT settlement"
    ],
    "next_best_actions": [
      "Initiate reversal in CBS if debit posted but NEFT failed",
      "Correct beneficiary details and re-initiate NEFT if data error identified",
      "Escalate to NPCI NEFT desk for settlement status",
      "Reconcile NEFT settlement with CBS",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "RTGS Transfer Failed",
    "investigation_steps": [
      "Retrieve RTGS transfer failure logs from CBS and RBI RTGS system",
      "Check error/return codes from RBI RTGS processing",
      "Verify debit posting in CBS",
      "Check RTGS transaction processing status for the disputed transaction",
      "Verify beneficiary account number and IFSC",
      "Review reconciliation records for RTGS settlement"
    ],
    "next_best_actions": [
      "Initiate reversal in CBS if debit posted but RTGS failed",
      "Correct beneficiary details and re-initiate RTGS if data error identified",
      "Escalate to RBI RTGS desk for settlement status",
      "Reconcile RTGS settlement with CBS",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "IMPS Transfer Failed",
    "investigation_steps": [
      "Retrieve IMPS transfer failure logs from CBS and NPCI IMPS system",
      "Check error/return codes from NPCI IMPS processing",
      "Verify debit posting in CBS",
      "Check IMPS transaction processing status for the disputed transaction",
      "Verify beneficiary mobile number and MMID or account number and IFSC",
      "Review reconciliation records for IMPS settlement"
    ],
    "next_best_actions": [
      "Initiate reversal in CBS if debit posted but IMPS failed",
      "Correct beneficiary details and re-initiate IMPS if data error identified",
      "Escalate to NPCI IMPS desk for settlement status",
      "Reconcile IMPS settlement with CBS",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Bill Payment Failed",
    "investigation_steps": [
      "Retrieve bill payment failure logs from digital banking platform and payment gateway",
      "Check error codes returned during bill payment attempt",
      "Verify account balance in CBS at time of payment",
      "Check BBPS or biller integration logs for payment failure",
      "Verify biller ID and consumer number used for payment",
      "Check if amount was debited despite payment failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but payment failed",
      "Verify biller details and re-initiate payment",
      "Escalate to BBPS or payment gateway if biller integration failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Utility Bill Payment Pending",
    "investigation_steps": [
      "Retrieve utility bill payment status from digital banking platform and BBPS",
      "Verify debit posting in CBS",
      "Check BBPS settlement status for the payment",
      "Verify biller credit status via BBPS transaction trace",
      "Review reconciliation records for pending biller credit"
    ],
    "next_best_actions": [
      "Follow up with BBPS for payment settlement to biller",
      "Escalate to biller or BBPS if settlement is delayed beyond prescribed cycle",
      "Initiate reversal if BBPS confirms payment failed",
      "Update CRM with payment status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Credit Card Bill Payment Failed",
    "investigation_steps": [
      "Retrieve credit card bill payment failure logs from digital banking platform",
      "Check error codes returned during payment attempt",
      "Verify source account balance in CBS",
      "Verify credit card account number and issuer details",
      "Check payment gateway or BBPS logs for credit card bill payment failure",
      "Verify if amount was debited despite payment failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but payment failed",
      "Verify credit card details and re-initiate payment",
      "Escalate to payment gateway or BBPS if integration failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Loan EMI Payment Failed",
    "investigation_steps": [
      "Retrieve loan EMI payment failure logs from digital banking platform and CBS",
      "Check error codes returned during EMI payment attempt",
      "Verify source account balance in CBS",
      "Verify loan account number and EMI amount",
      "Check if NACH debit for EMI was processed in NPCI NACH system",
      "Review loan CBS records for EMI due and payment posting"
    ],
    "next_best_actions": [
      "Manually post EMI payment to loan account in CBS if debit confirmed",
      "Retry NACH debit if balance/mandate issue resolved",
      "Escalate to loan operations team for manual EMI credit",
      "Escalate to NPCI NACH team if mandate failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Tax Payment Failed",
    "investigation_steps": [
      "Retrieve tax payment failure logs from digital banking platform",
      "Check error codes returned during tax payment attempt",
      "Verify source account balance in CBS",
      "Check TIN/NSDL/OLTAS payment gateway integration logs for failure",
      "Verify CIN (Challan Identification Number) generation status",
      "Check if amount was debited despite tax payment failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but tax payment failed",
      "Escalate to TIN/NSDL payment gateway team if integration failure confirmed",
      "Re-initiate tax payment after verifying payment details",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "GST Payment Failed",
    "investigation_steps": [
      "Retrieve GST payment failure logs from digital banking platform",
      "Check error codes returned during GST payment attempt",
      "Verify source account balance in CBS",
      "Check GSTN payment gateway integration logs for failure",
      "Verify CPIN (Challan Pre-filled Identification Number) details",
      "Check if amount was debited despite GST payment failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but GST payment failed",
      "Escalate to GSTN payment gateway team if integration failure confirmed",
      "Re-initiate GST payment after verifying CPIN and payment details",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Investment Payment Failed",
    "investigation_steps": [
      "Retrieve investment payment failure logs from digital banking platform",
      "Check error codes returned during investment payment attempt",
      "Verify source account balance in CBS",
      "Check investment gateway or BSE/NSE integration logs for failure",
      "Verify investment details: folio number, scheme, amount",
      "Check if amount was debited despite investment payment failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but investment payment failed",
      "Escalate to investment gateway or exchange integration team if failure confirmed",
      "Re-initiate investment payment after verifying details",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Merchant Payment Failed",
    "investigation_steps": [
      "Retrieve merchant payment failure logs from digital banking platform and payment gateway",
      "Check error codes returned during merchant payment attempt",
      "Verify source account balance in CBS",
      "Check payment gateway integration logs for merchant payment failure",
      "Verify merchant details and payment gateway used",
      "Check if amount was debited despite payment failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but merchant payment failed",
      "Escalate to payment gateway team if gateway failure confirmed",
      "Re-initiate payment after verifying merchant and payment details",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Payment Gateway Error",
    "investigation_steps": [
      "Retrieve payment gateway error logs from digital banking platform",
      "Check error codes returned by payment gateway",
      "Verify payment gateway uptime and service availability",
      "Check API integration logs between digital banking platform and payment gateway",
      "Verify if error is transaction-specific or affecting multiple transactions",
      "Check if amount was debited despite gateway error"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but transaction failed due to gateway error",
      "Escalate to payment gateway provider for service restoration",
      "Escalate to digital banking IT team for API integration review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Auto-Debit Registration Failed",
    "investigation_steps": [
      "Retrieve auto-debit registration request logs from digital banking platform",
      "Check error codes returned during registration attempt",
      "Verify account details and mandate parameters",
      "Check NPCI NACH/e-mandate registration logs for failure",
      "Verify OTP authentication logs for mandate registration",
      "Review biller/merchant mandate registration records"
    ],
    "next_best_actions": [
      "Retry auto-debit registration after resolving authentication or data issue",
      "Escalate to NPCI NACH team if mandate registration failure confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Mandate Registration Failed",
    "investigation_steps": [
      "Retrieve mandate registration request logs from digital banking platform",
      "Check error codes during NACH/e-mandate registration",
      "Verify mandate parameters: account number, IFSC, amount, frequency, validity",
      "Check NPCI NACH system for registration failure reason",
      "Verify OTP/Aadhaar authentication logs for mandate registration",
      "Check if destination bank accepted the mandate"
    ],
    "next_best_actions": [
      "Retry mandate registration after correcting parameters",
      "Escalate to NPCI NACH team if systemic registration failure confirmed",
      "Escalate to digital banking IT team if platform API failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Mandate Cancellation Failed",
    "investigation_steps": [
      "Retrieve mandate cancellation request logs from digital banking platform",
      "Check error codes during cancellation attempt",
      "Verify mandate status in NPCI NACH system",
      "Check if mandate is in active status eligible for cancellation",
      "Review digital banking platform processing queue for pending cancellation requests"
    ],
    "next_best_actions": [
      "Manually cancel mandate in NPCI NACH system",
      "Escalate to NPCI NACH team if systemic cancellation failure confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "AutoPay Setup Failed",
    "investigation_steps": [
      "Retrieve AutoPay setup request logs from digital banking platform",
      "Check error codes returned during AutoPay setup attempt",
      "Verify account details and AutoPay parameters",
      "Check NACH/e-mandate or UPI AutoPay registration logs",
      "Verify OTP authentication logs for AutoPay setup",
      "Review biller/merchant AutoPay setup records"
    ],
    "next_best_actions": [
      "Retry AutoPay setup after resolving authentication or data issue",
      "Escalate to NPCI NACH or UPI AutoPay system team if registration failure confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Profile Update Failed",
    "investigation_steps": [
      "Retrieve profile update request logs from digital banking platform",
      "Check error codes returned during profile update attempt",
      "Verify OTP or 2FA authentication logs for profile update",
      "Check CBS API connectivity for profile data update",
      "Review digital banking platform processing queue for pending update requests"
    ],
    "next_best_actions": [
      "Manually update profile in CBS and digital banking platform if system error confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Escalate to CBS team if CBS API failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Registered Mobile Number Not Updated",
    "investigation_steps": [
      "Verify mobile number update request in CRM and CBS",
      "Check CBS for current registered mobile number",
      "Review CBS update logs for mobile number update failure or pending status",
      "Verify OTP authentication for mobile number update",
      "Check system queue for pending mobile number update requests"
    ],
    "next_best_actions": [
      "Manually update registered mobile number in CBS",
      "Escalate to CBS/IT team if system update failure identified",
      "Notify customer via old and new mobile number upon update",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Email ID Not Updated",
    "investigation_steps": [
      "Verify email ID update request in CRM and CBS",
      "Check CBS for current registered email ID",
      "Review CBS update logs for email update failure or pending status",
      "Verify OTP or 2FA authentication for email update",
      "Check system queue for pending email update requests"
    ],
    "next_best_actions": [
      "Manually update registered email ID in CBS",
      "Escalate to CBS/IT team if system update failure identified",
      "Notify customer via old and new email upon update",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Address Update Pending",
    "investigation_steps": [
      "Verify address update request in CRM and CBS",
      "Check CBS for current registered address",
      "Review CBS update logs for address update failure or pending status",
      "Verify if KYC documents were submitted for address change",
      "Check KYC processing queue for pending document verification"
    ],
    "next_best_actions": [
      "Manually update registered address in CBS after KYC verification",
      "Escalate to KYC team if documents are pending review",
      "Update digital banking platform address after CBS update",
      "Update CRM with address change status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Nominee Update Failed",
    "investigation_steps": [
      "Retrieve nominee update request logs from digital banking platform",
      "Check error codes returned during nominee update attempt",
      "Verify OTP or 2FA authentication logs for nominee update",
      "Check CBS API connectivity for nominee data update",
      "Verify if required documentation for nominee update was submitted"
    ],
    "next_best_actions": [
      "Manually update nominee details in CBS if system error confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Escalate to CBS team if CBS update failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "PAN Update Failed",
    "investigation_steps": [
      "Retrieve PAN update request logs from digital banking platform",
      "Check error codes returned during PAN update attempt",
      "Verify PAN details submitted against Income Tax database records",
      "Check CBS API connectivity for PAN data update",
      "Verify KYC status and PAN linking eligibility in CBS"
    ],
    "next_best_actions": [
      "Manually update PAN in CBS after verification",
      "Escalate to KYC team for PAN validation and linking",
      "Escalate to digital banking IT team if platform failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "KYC Update Failed",
    "investigation_steps": [
      "Retrieve KYC update request logs from digital banking platform",
      "Check error codes returned during KYC update attempt",
      "Verify KYC documents submitted for update",
      "Check KYC management system for processing status",
      "Verify CBS KYC status and update API connectivity"
    ],
    "next_best_actions": [
      "Process KYC update manually in KYC management system and CBS",
      "Escalate to KYC team for expedited document processing",
      "Escalate to digital banking IT team if platform failure confirmed",
      "Update CBS with completed KYC status upon verification",
      "Update CRM with KYC update status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Profile Photo Upload Failed",
    "investigation_steps": [
      "Retrieve profile photo upload failure logs from digital banking platform",
      "Check error codes returned during photo upload attempt",
      "Verify photo file format and size against platform requirements",
      "Check digital banking platform storage service availability",
      "Review upload API logs for failure reason"
    ],
    "next_best_actions": [
      "Verify and correct photo file format/size requirements",
      "Escalate to digital banking IT team if storage service or upload API failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Cheque Book Request Failed",
    "investigation_steps": [
      "Retrieve cheque book request logs from digital banking platform and CBS",
      "Check error codes returned during request submission",
      "Verify account eligibility for cheque book issuance in CBS",
      "Check CBS API connectivity for cheque book request processing",
      "Verify registered delivery address in CBS"
    ],
    "next_best_actions": [
      "Manually submit cheque book request in CBS",
      "Escalate to digital banking IT team if platform failure identified",
      "Escalate to CBS team if CBS processing failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Cheque Book Tracking Unavailable",
    "investigation_steps": [
      "Verify cheque book dispatch status in CBS and courier records",
      "Check courier partner tracking integration with digital banking platform",
      "Verify dispatch date and courier tracking number in CBS",
      "Review courier partner tracking API logs for failure"
    ],
    "next_best_actions": [
      "Retrieve tracking details directly from courier partner records",
      "Escalate to digital banking IT team if courier tracking API integration failure confirmed",
      "Provide tracking details to customer via alternate channel",
      "Update CRM with tracking information"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Stop Cheque Payment Failed",
    "investigation_steps": [
      "Retrieve stop cheque request logs from digital banking platform and CBS",
      "Check error codes returned during stop cheque request",
      "Verify cheque number and account details in stop cheque request",
      "Check CBS for current stop cheque instruction status",
      "Verify if cheque was already presented or cleared before stop instruction"
    ],
    "next_best_actions": [
      "Manually process stop cheque instruction in CBS if not yet applied",
      "Initiate reversal/dispute if cheque was cleared after valid stop instruction",
      "Escalate to CBS team if CBS processing failure confirmed",
      "Update CRM with stop cheque status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Demand Draft Request Failed",
    "investigation_steps": [
      "Retrieve demand draft request logs from digital banking platform and CBS",
      "Check error codes returned during request submission",
      "Verify account balance in CBS for DD amount plus charges",
      "Check CBS API connectivity for DD request processing",
      "Verify DD payee name, amount, and delivery details"
    ],
    "next_best_actions": [
      "Manually process DD request in CBS",
      "Escalate to digital banking IT team if platform failure identified",
      "Escalate to CBS team if CBS processing failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Fixed Deposit Opening Failed",
    "investigation_steps": [
      "Retrieve FD opening request logs from digital banking platform and CBS",
      "Check error codes returned during FD opening attempt",
      "Verify source account balance in CBS for FD amount",
      "Check CBS API connectivity for FD account creation",
      "Verify FD parameters: amount, tenure, interest payout option",
      "Check if amount was debited despite FD opening failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but FD not opened",
      "Manually process FD opening in CBS if system error confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Escalate to CBS team if CBS FD creation failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Recurring Deposit Opening Failed",
    "investigation_steps": [
      "Retrieve RD opening request logs from digital banking platform and CBS",
      "Check error codes returned during RD opening attempt",
      "Verify source account balance in CBS for first RD installment",
      "Check CBS API connectivity for RD account creation",
      "Verify RD parameters: installment amount, tenure, frequency",
      "Check if amount was debited despite RD opening failure"
    ],
    "next_best_actions": [
      "Initiate reversal if amount debited but RD not opened",
      "Manually process RD opening in CBS if system error confirmed",
      "Escalate to digital banking IT team if platform failure identified",
      "Escalate to CBS team if CBS RD creation failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Loan Statement Download Failed",
    "investigation_steps": [
      "Retrieve loan statement download failure logs from digital banking platform",
      "Check error codes returned during download attempt",
      "Verify loan account number and CBS API connectivity for loan statement data",
      "Check loan CBS records for statement data availability",
      "Verify statement generation service availability in digital banking platform"
    ],
    "next_best_actions": [
      "Retry loan statement generation from CBS",
      "Escalate to digital banking IT team if statement generation service failure confirmed",
      "Provide loan statement via alternate channel (email/branch) as interim resolution",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Interest Certificate Not Available",
    "investigation_steps": [
      "Verify interest certificate generation status in CBS and digital banking platform",
      "Check if interest certificate is available for the requested financial year",
      "Review CBS data for interest accrual and posting records",
      "Check digital banking platform certificate generation service logs",
      "Verify account type and eligibility for interest certificate"
    ],
    "next_best_actions": [
      "Generate interest certificate from CBS and deliver via digital banking platform or email",
      "Escalate to CBS team if interest data is unavailable for the period",
      "Escalate to digital banking IT team if certificate generation service failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "TDS Certificate Not Available",
    "investigation_steps": [
      "Verify TDS certificate (Form 16A) generation status in CBS and TDS system",
      "Check if TDS was deducted for the requested financial year in CBS",
      "Verify TDS filing and certificate generation with TRACES/TDSCPC",
      "Check digital banking platform TDS certificate availability and generation logs",
      "Confirm account type and eligibility for TDS deduction"
    ],
    "next_best_actions": [
      "Generate TDS certificate from TRACES and deliver via digital banking platform or email",
      "Escalate to tax/compliance team if TDS filing issue identified",
      "Escalate to digital banking IT team if certificate display failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Account Statement Incorrect",
    "investigation_steps": [
      "Retrieve account statement from CBS for the disputed period",
      "Compare CBS statement against statement displayed/downloaded via digital banking platform",
      "Identify specific incorrect entries: missing, duplicate, or wrong amount",
      "Verify CBS-to-digital banking data mapping for statement generation",
      "Check reconciliation records for disputed transactions"
    ],
    "next_best_actions": [
      "Correct statement data in digital banking platform if data mapping error identified",
      "Escalate to CBS team if incorrect entries exist in CBS itself",
      "Reconcile disputed transaction entries",
      "Provide corrected statement from CBS as authoritative record",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Download Receipt Not Generated",
    "investigation_steps": [
      "Retrieve transaction receipt generation logs from digital banking platform",
      "Check error codes during receipt generation attempt",
      "Verify transaction completion status in CBS for the specific transaction",
      "Check receipt generation service availability in digital banking platform",
      "Verify transaction reference number for receipt generation"
    ],
    "next_best_actions": [
      "Manually generate and deliver transaction receipt from CBS records",
      "Escalate to digital banking IT team if receipt generation service failure confirmed",
      "Provide transaction acknowledgment via email as interim resolution",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "SMS Alert Not Received",
    "investigation_steps": [
      "Verify SMS alert configuration in CBS and notification system",
      "Check SMS gateway delivery logs for the disputed alert",
      "Verify registered mobile number in CBS",
      "Check if mobile number is DND registered",
      "Review telecom carrier routing for the registered number",
      "Check SMS gateway provider logs for delivery failure reason"
    ],
    "next_best_actions": [
      "Update registered mobile number in CBS if incorrect",
      "Escalate to SMS gateway provider if delivery failure confirmed",
      "Check and resolve DND registration if applicable",
      "Escalate to notification/digital banking team for SMS service review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Email Alert Not Received",
    "investigation_steps": [
      "Verify email alert configuration in CBS and notification system",
      "Check email delivery logs for the disputed alert",
      "Verify registered email ID in CBS",
      "Check if email was delivered to spam or junk folder",
      "Review email service provider delivery status for the alert",
      "Check email service provider bounce or rejection logs"
    ],
    "next_best_actions": [
      "Update registered email ID in CBS if incorrect",
      "Escalate to email service provider if delivery failure confirmed",
      "Escalate to notification/digital banking team for email alert service review",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Push Notification Not Received",
    "investigation_steps": [
      "Verify push notification configuration in digital banking platform",
      "Check push notification delivery logs for the disputed notification",
      "Verify device registration and push notification token in digital banking platform",
      "Check push notification gateway (FCM/APNs) delivery status",
      "Verify if customer has disabled push notifications on device"
    ],
    "next_best_actions": [
      "Escalate to digital banking IT team if push notification service failure confirmed",
      "Verify and refresh push notification token registration in platform",
      "Escalate to push notification gateway provider if delivery failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Security Alert Not Received",
    "investigation_steps": [
      "Verify security alert configuration in digital banking platform and notification system",
      "Check SMS and email delivery logs for the security alert",
      "Verify registered mobile number and email ID in CBS",
      "Check if security alert trigger event was logged in platform",
      "Review notification gateway logs for security alert delivery failure"
    ],
    "next_best_actions": [
      "Update registered mobile number or email in CBS if incorrect",
      "Escalate to digital banking IT team if security alert service failure confirmed",
      "Review and fix security alert trigger and delivery workflow",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Suspicious Login Detected",
    "investigation_steps": [
      "Retrieve login logs from digital banking platform for suspicious login event",
      "Check login geolocation, IP address, and device fingerprint",
      "Compare login details against customer's known profile and past login patterns",
      "Review fraud management system for risk score on suspicious login",
      "Check if any transactions were initiated post suspicious login",
      "Verify if customer was alerted via SMS/email for the login"
    ],
    "next_best_actions": [
      "Block internet banking access pending customer verification",
      "Force password reset and 2FA re-enrollment",
      "Escalate to fraud management and security team",
      "Initiate chargeback for any unauthorized transactions post suspicious login",
      "Update CRM with security incident details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Unauthorized Login Attempt",
    "investigation_steps": [
      "Retrieve failed login attempt logs from digital banking platform",
      "Check IP address, geolocation, and device fingerprint of login attempts",
      "Review fraud management system for brute-force or credential stuffing pattern",
      "Verify if account was auto-locked after threshold failed attempts",
      "Check if customer was alerted via SMS/email for failed login attempts"
    ],
    "next_best_actions": [
      "Lock user account if not already locked",
      "Force password reset upon customer identity verification",
      "Escalate to fraud management and security team",
      "Block suspicious IP address at platform level if attack pattern confirmed",
      "Update CRM with security incident details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Unauthorized Transaction",
    "investigation_steps": [
      "Retrieve transaction details from CBS and digital banking platform logs",
      "Verify authentication method used for transaction (OTP/2FA/PIN)",
      "Check login session details: IP address, device, geolocation",
      "Review OTP delivery logs for transaction authentication",
      "Check if login was from a new/unregistered device",
      "Review fraud management system risk score for the transaction"
    ],
    "next_best_actions": [
      "Block internet banking access immediately",
      "Initiate chargeback or recall for unauthorized transaction",
      "Force password reset and 2FA re-enrollment",
      "Escalate to fraud management team",
      "Initiate provisional credit to customer account pending investigation",
      "Update CRM with fraud incident details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Fraudulent Transaction",
    "investigation_steps": [
      "Retrieve transaction details from CBS and digital banking platform logs",
      "Verify authentication method used for fraudulent transaction",
      "Check login session details: IP address, device fingerprint, geolocation",
      "Review OTP delivery and usage logs",
      "Review fraud management system alerts and risk score",
      "Cross-reference with known fraud patterns in fraud management system"
    ],
    "next_best_actions": [
      "Block internet banking access immediately",
      "Initiate chargeback or fund recall for fraudulent transaction",
      "Force password reset and 2FA re-enrollment",
      "Escalate to fraud management team for investigation",
      "Initiate provisional credit to customer account",
      "Report fraud case to NPCI/RBI if applicable",
      "Update CRM with fraud incident details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Session Hijacking Concern",
    "investigation_steps": [
      "Retrieve active session logs from digital banking platform for the concerned session",
      "Check session token validity and binding to IP address and device",
      "Verify if session was accessed from multiple IP addresses simultaneously",
      "Review security logs for session token theft or replay attack indicators",
      "Check if any transactions were initiated during the potentially hijacked session",
      "Review fraud management system for anomaly alerts on the session"
    ],
    "next_best_actions": [
      "Terminate all active sessions for the customer immediately",
      "Force password reset and 2FA re-enrollment",
      "Block internet banking access pending security review",
      "Escalate to security and fraud management team",
      "Initiate chargeback for any unauthorized transactions during session",
      "Escalate to digital banking IT team for session security review",
      "Update CRM with security incident details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Digital Signature Verification Failed",
    "investigation_steps": [
      "Retrieve digital signature verification failure logs from digital banking platform",
      "Check error codes returned during digital signature verification",
      "Verify digital certificate validity and issuing CA status",
      "Check if digital certificate is expired, revoked, or mismatched",
      "Verify digital signature service (DSC/PKI) availability and integration logs"
    ],
    "next_best_actions": [
      "Reissue or renew digital certificate if expired or revoked",
      "Escalate to digital banking IT team if PKI/DSC integration failure confirmed",
      "Escalate to certifying authority if certificate revocation issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Captcha Not Loading",
    "investigation_steps": [
      "Verify captcha service availability and provider status",
      "Check digital banking platform frontend logs for captcha loading failure",
      "Review captcha service integration API logs",
      "Verify if third-party captcha provider (reCAPTCHA/hCaptcha) service is operational",
      "Check if browser or network settings are blocking captcha from loading"
    ],
    "next_best_actions": [
      "Escalate to digital banking IT team if captcha service integration failure confirmed",
      "Escalate to captcha service provider if provider-side outage identified",
      "Implement alternate captcha solution as interim measure if available",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Captcha Verification Failed",
    "investigation_steps": [
      "Retrieve captcha verification failure logs from digital banking platform",
      "Check error codes returned during captcha verification",
      "Verify captcha service integration API response",
      "Check if captcha failure is user-specific or affecting multiple users",
      "Review if captcha challenge-response cycle is functioning correctly"
    ],
    "next_best_actions": [
      "Retry captcha verification with fresh challenge",
      "Escalate to digital banking IT team if captcha verification system failure confirmed",
      "Escalate to captcha service provider if provider-side failure identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Internet Banking Access Blocked",
    "investigation_steps": [
      "Verify internet banking access block status and reason in digital banking platform",
      "Check if block was triggered by fraud rule, security policy, or manual action",
      "Review failed login and security event logs associated with block",
      "Verify if compliance or regulatory hold caused access block",
      "Check CBS account status linked to internet banking profile"
    ],
    "next_best_actions": [
      "Unblock internet banking access after identity verification if block was erroneous",
      "Force password reset and 2FA re-enrollment post unblock",
      "Escalate to security team if fraud-triggered block confirmed",
      "Escalate to compliance team if regulatory hold identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Dormant Internet Banking Account",
    "investigation_steps": [
      "Verify internet banking account dormancy status in digital banking platform",
      "Check last login date and activity in digital banking platform",
      "Verify CBS account status (active/dormant/inoperative)",
      "Review dormancy activation policy in digital banking platform",
      "Check if dormancy was triggered by inactivity threshold"
    ],
    "next_best_actions": [
      "Reactivate internet banking account in digital banking platform after identity verification",
      "Reactivate CBS account if dormant at CBS level",
      "Initiate re-KYC if required for reactivation",
      "Update CRM with reactivation status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Account Mapping Incorrect",
    "investigation_steps": [
      "Verify account mapping in digital banking platform and CBS",
      "Check if correct accounts are linked to the internet banking customer profile",
      "Review digital banking platform account linkage configuration",
      "Verify CBS customer ID and account relationships",
      "Check if data migration or system upgrade caused mapping error"
    ],
    "next_best_actions": [
      "Correct account mapping in digital banking platform and CBS",
      "Escalate to digital banking IT team for account linkage correction",
      "Reconcile any transactions impacted by incorrect mapping",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Linked Account Not Visible",
    "investigation_steps": [
      "Verify account linkage in digital banking platform",
      "Check CBS for all accounts under the customer ID",
      "Review digital banking platform account display configuration",
      "Check if account was recently opened and pending linkage in platform",
      "Verify if account type is supported for display in digital banking platform"
    ],
    "next_best_actions": [
      "Link missing account to customer profile in digital banking platform",
      "Escalate to digital banking IT team if account linkage failure confirmed",
      "Escalate to CBS team if CBS account relationship data issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Joint Account Not Visible",
    "investigation_steps": [
      "Verify joint account linkage in digital banking platform",
      "Check CBS for joint account relationship under the customer ID",
      "Review digital banking platform joint account display configuration",
      "Verify if all joint account holders are registered for internet banking",
      "Check if joint account operating mandate affects digital banking access"
    ],
    "next_best_actions": [
      "Link joint account to customer profile in digital banking platform",
      "Escalate to digital banking IT team if joint account linkage failure confirmed",
      "Escalate to CBS team if CBS joint account relationship data issue identified",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Service Request Not Submitted",
    "investigation_steps": [
      "Retrieve service request submission logs from digital banking platform",
      "Check error codes returned during service request submission attempt",
      "Verify OTP or 2FA authentication logs for service request submission",
      "Check digital banking platform service request processing queue",
      "Review CBS API connectivity for service request routing"
    ],
    "next_best_actions": [
      "Manually submit service request in CBS or digital banking platform",
      "Escalate to digital banking IT team if platform submission failure confirmed",
      "Escalate to CBS team if CBS API failure identified",
      "Update CRM with service request submission status"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Service Request Status Not Updated",
    "investigation_steps": [
      "Verify service request status in CRM and CBS",
      "Check digital banking platform for service request status display",
      "Review CBS-to-digital banking status sync logs",
      "Check service request processing queue for pending status updates",
      "Verify if service request was processed in CBS but status not reflected in platform"
    ],
    "next_best_actions": [
      "Trigger manual status sync between CBS and digital banking platform",
      "Update service request status in digital banking platform",
      "Escalate to digital banking IT team if sync failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Complaint Registration Failed",
    "investigation_steps": [
      "Retrieve complaint registration failure logs from digital banking platform",
      "Check error codes returned during complaint submission attempt",
      "Verify digital banking platform CRM integration logs",
      "Check if complaint management system API is operational",
      "Review platform processing queue for failed complaint registrations"
    ],
    "next_best_actions": [
      "Manually register complaint in CRM on behalf of customer",
      "Escalate to digital banking IT team if complaint submission service failure confirmed",
      "Escalate to CRM team if integration failure identified",
      "Update CRM with manually registered complaint details"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Complaint Status Not Updated",
    "investigation_steps": [
      "Verify complaint status in CRM",
      "Check digital banking platform for complaint status display",
      "Review CRM-to-digital banking status sync logs",
      "Check complaint processing queue for pending status updates",
      "Verify if complaint was resolved in CRM but status not reflected in platform"
    ],
    "next_best_actions": [
      "Trigger manual status sync between CRM and digital banking platform",
      "Update complaint status in digital banking platform to match CRM",
      "Escalate to digital banking IT team if sync failure confirmed",
      "Update CRM with corrective action taken"
    ]
  },
  {
    "major_issue": "Internet Banking",
    "sub_issue": "Internet Banking Deactivation Failed",
    "investigation_steps": [
      "Retrieve internet banking deactivation request logs from digital banking platform",
      "Check error codes returned during deactivation attempt",
      "Verify current internet banking status in digital banking platform",
      "Review digital banking platform processing queue for pending deactivation requests",
      "Check if any active standing instructions or scheduled payments are linked to profile"
    ],
    "next_best_actions": [
      "Manually deactivate internet banking profile in digital banking platform",
      "Block access as interim security measure if deactivation is critical",
      "Escalate to digital banking IT team if platform deactivation failure confirmed",
      "Update CRM with deactivation status"
    ]
  }
],
[
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Mobile Banking Registration Failed",
    "investigation_steps": [
      "Check registration request log in mobile banking middleware/API gateway",
      "Verify CBS customer/account validation response during registration",
      "Review error/response code returned at the point of failure",
      "Check device binding and channel activation log"
    ],
    "next_best_actions": [
      "Retry registration after correcting validation failure",
      "Escalate to digital banking/middleware team if API error confirmed",
      "Update CBS channel activation flag",
      "Verify successful registration post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Unable to Register Mobile Banking",
    "investigation_steps": [
      "Check customer eligibility flag (KYC, account status) in CBS for channel registration",
      "Verify middleware log for registration request rejection reason",
      "Review mobile number/Aadhaar-linked verification status"
    ],
    "next_best_actions": [
      "Correct eligibility/KYC flag in CBS if blocking registration",
      "Escalate to middleware team for API-level rejection fix",
      "Re-trigger registration workflow",
      "Confirm registration completion with test login"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Device Registration Failed",
    "investigation_steps": [
      "Check device binding API log for the registration request",
      "Verify device fingerprint/IMEI capture and validation log",
      "Review device management system for duplicate/blacklisted device entry"
    ],
    "next_best_actions": [
      "Clear blocked/duplicate device entry if erroneous",
      "Retry device registration request",
      "Escalate to mobile app/device management team for API fix",
      "Verify device successfully bound post-correction"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Mobile Number Verification Failed",
    "investigation_steps": [
      "Check OTP gateway delivery log for the verification request",
      "Verify registered mobile number mapping in CBS against entered number",
      "Review verification API response code from telecom/OTP service provider"
    ],
    "next_best_actions": [
      "Resend verification OTP",
      "Correct mobile number mapping in CBS if mismatched",
      "Escalate to OTP/SMS gateway vendor if delivery failure confirmed",
      "Verify successful number verification post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Mobile Banking Login Failed",
    "investigation_steps": [
      "Check authentication server log for login response code",
      "Verify CBS/channel user profile status (active/locked/blocked)",
      "Review middleware log for session establishment failure",
      "Cross-check device binding status against login device"
    ],
    "next_best_actions": [
      "Unlock/reset user profile status if erroneously restricted",
      "Escalate to authentication/middleware team for API-level error",
      "Retry login session establishment",
      "Verify successful login post-correction"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Invalid Username or Password",
    "investigation_steps": [
      "Check authentication server log for credential validation response",
      "Verify username mapping and password hash status in CBS/identity system",
      "Review failed login attempt count and lockout threshold configuration"
    ],
    "next_best_actions": [
      "Reset password/credentials if account verified as genuine user",
      "Unlock account if lockout triggered incorrectly",
      "Escalate to identity management team if hash/mapping error found",
      "Verify successful login post-reset"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Biometric Login Failed",
    "investigation_steps": [
      "Check biometric SDK/authentication module response log",
      "Verify biometric template enrollment status on device versus server",
      "Review device compatibility and OS-level biometric API logs"
    ],
    "next_best_actions": [
      "Re-enroll biometric template if corrupted",
      "Escalate to mobile app vendor for SDK-level fix",
      "Advise fallback to MPIN/password login channel",
      "Verify biometric login post-re-enrollment"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Fingerprint Authentication Failed",
    "investigation_steps": [
      "Check fingerprint authentication module response/error log",
      "Verify fingerprint template enrollment and match-score threshold configuration",
      "Review device hardware sensor diagnostic log if available"
    ],
    "next_best_actions": [
      "Re-enroll fingerprint template",
      "Escalate to vendor for SDK/sensor calibration issue",
      "Adjust match-score threshold if misconfigured",
      "Verify fix with test authentication"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Face ID Authentication Failed",
    "investigation_steps": [
      "Check Face ID/facial recognition module response log",
      "Verify facial template enrollment status and liveness check configuration",
      "Review device camera/OS-level API compatibility log"
    ],
    "next_best_actions": [
      "Re-enroll facial recognition template",
      "Escalate to vendor for SDK-level fix",
      "Advise fallback to MPIN/password login",
      "Verify fix with test authentication"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "MPIN Generation Failed",
    "investigation_steps": [
      "Check CBS/channel MPIN generation request log and response code",
      "Verify HSM/encryption module log for MPIN creation transaction",
      "Review OTP verification log used for MPIN generation"
    ],
    "next_best_actions": [
      "Re-trigger MPIN generation request",
      "Escalate to HSM/security team if cryptographic failure confirmed",
      "Correct OTP/authentication mapping if verification failed incorrectly",
      "Verify MPIN generation success post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "MPIN Reset Failed",
    "investigation_steps": [
      "Check CBS/channel MPIN reset request status and error code",
      "Verify HSM log for reset transaction response",
      "Review authentication/OTP verification log used for reset"
    ],
    "next_best_actions": [
      "Re-initiate MPIN reset process",
      "Escalate to HSM/security team for cryptographic failure",
      "Correct authentication mapping if verification failed incorrectly",
      "Verify MPIN reset success post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Forgot MPIN",
    "investigation_steps": [
      "Verify customer identity through registered authentication channel",
      "Check CBS/channel MPIN reset workflow availability for the account",
      "Review account status for any restriction preventing MPIN reset"
    ],
    "next_best_actions": [
      "Initiate MPIN reset workflow for the customer",
      "Remove restriction flag if account erroneously blocked",
      "Trigger OTP-based reset verification",
      "Confirm new MPIN setup completion"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Incorrect MPIN",
    "investigation_steps": [
      "Check authentication server log for MPIN validation response",
      "Verify failed attempt count against lockout threshold configuration",
      "Review HSM log for PIN block translation/validation error"
    ],
    "next_best_actions": [
      "Advise MPIN reset if customer-side error confirmed",
      "Escalate to HSM/security team if validation logic error identified",
      "Reset failed attempt counter if found incorrectly incremented",
      "Verify resolution with test login"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "MPIN Locked",
    "investigation_steps": [
      "Check failed MPIN attempt log and lockout trigger timestamp",
      "Verify lockout threshold and cool-down period configuration",
      "Review CBS/channel account status for lock flag"
    ],
    "next_best_actions": [
      "Unlock MPIN/account post identity verification",
      "Reset MPIN if required",
      "Correct lockout threshold configuration if misconfigured",
      "Verify account access restored"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "OTP Not Received",
    "investigation_steps": [
      "Check OTP gateway delivery log for the transaction/login request",
      "Verify registered mobile number mapping in CBS",
      "Review OTP generation/trigger log at application/middleware level"
    ],
    "next_best_actions": [
      "Resend OTP request",
      "Correct mobile number mapping if found incorrect",
      "Escalate to OTP/SMS gateway vendor if delivery failure confirmed",
      "Verify OTP delivery post-correction"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "OTP Verification Failed",
    "investigation_steps": [
      "Check OTP validation log at application/middleware level for response code",
      "Verify OTP generated versus OTP entered for time-window match",
      "Review server-client time synchronization for OTP validity window"
    ],
    "next_best_actions": [
      "Resend OTP and retry verification",
      "Escalate to middleware team if validation logic error confirmed",
      "Correct time synchronization configuration if mismatch found",
      "Verify successful OTP verification post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "OTP Expired",
    "investigation_steps": [
      "Check OTP generation and expiry timestamp log against verification attempt time",
      "Verify OTP validity window configuration in application/middleware system",
      "Review delivery log for transmission delay causing expiry"
    ],
    "next_best_actions": [
      "Regenerate OTP for customer to retry",
      "Adjust OTP validity window if configuration found too short",
      "Escalate to gateway team if delivery delay caused expiry",
      "Verify resolution with test transaction"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "App Crashing",
    "investigation_steps": [
      "Check application crash log/stack trace from crash reporting tool",
      "Verify app version and OS compatibility matrix",
      "Review device-specific crash pattern (model, OS version) for affected users"
    ],
    "next_best_actions": [
      "Escalate to mobile app development team for crash fix",
      "Issue hotfix/patch release for the affected app version",
      "Advise app reinstall/cache clear as interim workaround",
      "Monitor crash rate post-fix deployment"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "App Not Opening",
    "investigation_steps": [
      "Check app launch/crash log from crash reporting tool",
      "Verify app version compatibility with device OS version",
      "Review server-side health check for app initialization API dependency"
    ],
    "next_best_actions": [
      "Escalate to mobile app development team for launch failure fix",
      "Advise app update/reinstall as interim workaround",
      "Restore backend initialization service if found down",
      "Verify fix with test app launch"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "App Keeps Logging Out",
    "investigation_steps": [
      "Check session management log for premature session termination cause",
      "Verify session timeout and token refresh configuration",
      "Review token/session storage log on app and server side"
    ],
    "next_best_actions": [
      "Correct session timeout/token refresh configuration",
      "Escalate to backend/session management team for fix",
      "Clear corrupted session cache if device-specific",
      "Verify session stability post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Session Timed Out",
    "investigation_steps": [
      "Check session timeout configuration against actual session duration logged",
      "Verify server/middleware response latency for the session",
      "Review token expiry and refresh mechanism logs"
    ],
    "next_best_actions": [
      "Adjust session timeout threshold if misconfigured",
      "Escalate to backend team if latency-related timeout confirmed",
      "Reverse any transaction impacted by premature timeout",
      "Verify session behavior post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "App Running Slowly",
    "investigation_steps": [
      "Check application performance monitoring (APM) log for response time metrics",
      "Verify server/API latency logs for the affected period",
      "Review device-specific performance pattern (model, OS, network type)"
    ],
    "next_best_actions": [
      "Escalate to backend/infrastructure team for performance tuning",
      "Optimize API/database query response time",
      "Advise app cache clear/update as interim workaround",
      "Monitor performance metrics post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "App Freezing",
    "investigation_steps": [
      "Check application crash/hang log from monitoring tool",
      "Verify memory/resource utilization log on app and server side",
      "Review device-specific freeze pattern for affected users"
    ],
    "next_best_actions": [
      "Escalate to mobile app development team for freeze/hang fix",
      "Issue hotfix/patch release for the affected version",
      "Advise app reinstall/cache clear as interim workaround",
      "Monitor freeze incident rate post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Blank Screen After Login",
    "investigation_steps": [
      "Check post-login API call log for dashboard data retrieval failure",
      "Verify application rendering/UI module error log",
      "Review server response for dashboard/home screen data service"
    ],
    "next_best_actions": [
      "Escalate to backend team if data service failure confirmed",
      "Escalate to app development team for UI rendering fix",
      "Restart affected backend service if found down",
      "Verify fix with test login"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Server Unavailable",
    "investigation_steps": [
      "Check server health monitoring dashboard for uptime status",
      "Verify infrastructure/load balancer logs for outage cause",
      "Review incident management log for ongoing service disruption"
    ],
    "next_best_actions": [
      "Escalate to infrastructure/DevOps team for service restoration",
      "Failover to backup/disaster recovery server if configured",
      "Communicate service status update to relevant teams",
      "Monitor server availability post-restoration"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Maintenance Downtime",
    "investigation_steps": [
      "Check scheduled maintenance window log against reported downtime",
      "Verify maintenance task completion status",
      "Review system status dashboard for residual downtime beyond planned window"
    ],
    "next_best_actions": [
      "Expedite pending maintenance task completion",
      "Restore service availability post-maintenance",
      "Update maintenance schedule communication if overrun occurred",
      "Verify system functionality post-maintenance"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Internet Connection Error",
    "investigation_steps": [
      "Check app-side network connectivity error log",
      "Verify server/API endpoint availability and response status",
      "Review CDN/network routing logs for regional connectivity issues"
    ],
    "next_best_actions": [
      "Escalate to network/infrastructure team if server-side connectivity issue confirmed",
      "Advise customer-side network troubleshooting if device-specific",
      "Verify API endpoint reachability post-fix",
      "Monitor connectivity error rate post-resolution"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Unable to Access Mobile Banking",
    "investigation_steps": [
      "Check channel access status flag in CBS for the customer account",
      "Verify authentication/login log for access denial reason",
      "Review server/application health status for the affected period"
    ],
    "next_best_actions": [
      "Restore channel access if erroneously restricted",
      "Escalate to backend team if service outage confirmed",
      "Reset login credentials if access blocked due to lockout",
      "Verify access restored with test login"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Dashboard Not Loading",
    "investigation_steps": [
      "Check dashboard data API response log for error/timeout",
      "Verify backend service status for account summary/dashboard module",
      "Review app-side rendering log for dashboard component failure"
    ],
    "next_best_actions": [
      "Escalate to backend team if API/service failure confirmed",
      "Restart affected dashboard data service",
      "Escalate to app team for rendering-level fix",
      "Verify dashboard loads correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Account Balance Not Updated",
    "investigation_steps": [
      "Check CBS posting log for the latest transaction against displayed balance",
      "Verify data sync job/cache refresh log between CBS and mobile banking middleware",
      "Cross-check batch/real-time balance update process status"
    ],
    "next_best_actions": [
      "Trigger manual balance sync/cache refresh",
      "Escalate to middleware/integration team if sync job failure confirmed",
      "Verify CBS posting completeness for pending transactions",
      "Confirm balance displays correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Transaction History Not Loading",
    "investigation_steps": [
      "Check transaction history API response log for error/timeout",
      "Verify backend data retrieval service status for the history module",
      "Review app-side rendering log for history screen component failure"
    ],
    "next_best_actions": [
      "Escalate to backend team if API/service failure confirmed",
      "Restart affected transaction history service",
      "Escalate to app team for rendering-level fix",
      "Verify history loads correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Transaction History Missing",
    "investigation_steps": [
      "Check CBS transaction log retrieval query for the account",
      "Verify data sync/archival status between CBS and mobile banking data store",
      "Cross-check API pagination/query parameter logic for missing entries"
    ],
    "next_best_actions": [
      "Restore missing transaction entries from archival/backup data",
      "Escalate to IT/data team for sync or query logic fix",
      "Update mobile banking transaction history cache",
      "Verify resolution by re-querying transaction history"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Mini Statement Not Available",
    "investigation_steps": [
      "Check mini-statement API response log for error/timeout",
      "Verify CBS data retrieval response for the mini-statement request",
      "Review backend service status for the mini-statement module"
    ],
    "next_best_actions": [
      "Escalate to backend team if API/service failure confirmed",
      "Restart affected mini-statement service",
      "Retry mini-statement request processing",
      "Verify mini-statement displays correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Fund Transfer Failed",
    "investigation_steps": [
      "Check CBS authorization log and response code for the transfer request",
      "Verify middleware/payment gateway log for transaction routing status",
      "Review beneficiary account validation log",
      "Cross-check NPCI/network response for the transaction"
    ],
    "next_best_actions": [
      "Reverse any debit without successful credit",
      "Retry transfer processing if technical decline confirmed",
      "Escalate to payment gateway/switch team if recurring",
      "Update CBS records"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Fund Transfer Pending",
    "investigation_steps": [
      "Check transaction status in payment gateway/switch queue",
      "Verify CBS hold/pending entry against the transaction",
      "Review NPCI/network settlement file for matching entry"
    ],
    "next_best_actions": [
      "Auto-reverse pending transaction post TAT if unresolved",
      "Update CBS to release hold/complete credit upon confirmation",
      "Reconcile with settlement file",
      "Escalate unresolved pending entries to payment network team"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Amount Debited but Beneficiary Not Credited",
    "investigation_steps": [
      "Check CBS debit entry against payment gateway transaction status",
      "Verify NPCI/network settlement file for credit confirmation at beneficiary bank",
      "Review beneficiary bank response code (IMPS/NEFT/RTGS/UPI) for the transaction"
    ],
    "next_best_actions": [
      "Initiate reversal/refund if beneficiary credit not confirmed",
      "Raise tracer/inquiry with beneficiary bank via network if applicable",
      "Update CBS records post-resolution",
      "Reconcile with settlement file"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Amount Debited but Transfer Failed",
    "investigation_steps": [
      "Check CBS debit entry against payment gateway/switch failure response",
      "Verify middleware log for transaction failure point",
      "Cross-check NPCI/network response code for the failed transaction"
    ],
    "next_best_actions": [
      "Initiate reversal for the debited amount",
      "Update CBS records",
      "Escalate to payment gateway/switch team if recurring",
      "Reconcile with settlement file"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Duplicate Fund Transfer",
    "investigation_steps": [
      "Check CBS for multiple debit entries against single customer-initiated request",
      "Verify middleware/gateway retry or retransmission logs",
      "Cross-check payment network log for duplicate transaction submission"
    ],
    "next_best_actions": [
      "Reverse the duplicate transfer amount",
      "Update CBS records",
      "Escalate to middleware/gateway team to prevent retry duplication",
      "Reconcile with settlement file"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Transfer Reversed Unexpectedly",
    "investigation_steps": [
      "Check CBS reversal entry against original transaction record",
      "Verify payment gateway/network reversal message log",
      "Cross-check beneficiary bank response for reversal trigger reason"
    ],
    "next_best_actions": [
      "Correct reversal entry in CBS if erroneous",
      "Re-process transfer if reversal found incorrect",
      "Reconcile with settlement file",
      "Escalate to network/gateway team if reversal message error identified"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Beneficiary Addition Failed",
    "investigation_steps": [
      "Check CBS/beneficiary management module log for addition request status",
      "Verify beneficiary account/IFSC validation response",
      "Review API/middleware error code for the addition request"
    ],
    "next_best_actions": [
      "Retry beneficiary addition after correcting validation error",
      "Escalate to middleware team if API-level error confirmed",
      "Update CBS beneficiary master records",
      "Verify beneficiary added successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Beneficiary Activation Pending",
    "investigation_steps": [
      "Check beneficiary activation workflow status and cooling-period timer log",
      "Verify CBS/risk policy configuration for activation TAT",
      "Cross-check activation trigger job/batch status"
    ],
    "next_best_actions": [
      "Manually trigger activation if cooling period elapsed",
      "Escalate to risk/operations team for workflow delay",
      "Update CBS beneficiary status records",
      "Verify beneficiary reflects as active post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Beneficiary Verification Failed",
    "investigation_steps": [
      "Check beneficiary account/name/IFSC verification API response log",
      "Verify penny-drop/account validation service log for the request",
      "Review CBS beneficiary master data for mismatch"
    ],
    "next_best_actions": [
      "Retry beneficiary verification request",
      "Escalate to verification service provider if API failure confirmed",
      "Correct beneficiary data if mismatch identified",
      "Verify successful beneficiary verification post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Beneficiary Modification Failed",
    "investigation_steps": [
      "Check beneficiary management module log for modification request status",
      "Verify validation response for updated beneficiary details",
      "Review API/middleware error code for the modification request"
    ],
    "next_best_actions": [
      "Retry modification after correcting validation error",
      "Escalate to middleware team if API-level error confirmed",
      "Update CBS beneficiary master records",
      "Verify modification reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Beneficiary Removal Failed",
    "investigation_steps": [
      "Check beneficiary management module log for removal request status",
      "Verify CBS/middleware error code for the removal request",
      "Review any dependency (pending transaction/standing instruction) blocking removal"
    ],
    "next_best_actions": [
      "Retry removal after clearing blocking dependency",
      "Escalate to middleware team if API-level error confirmed",
      "Update CBS beneficiary master records",
      "Verify beneficiary removed successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Incorrect Beneficiary Credited",
    "investigation_steps": [
      "Check CBS/payment gateway log for beneficiary account number entered versus credited account",
      "Verify NPCI/network transaction trace for the credited account details",
      "Review beneficiary master data mapping for data entry error"
    ],
    "next_best_actions": [
      "Raise beneficiary bank inquiry/recall request via network",
      "Initiate reversal/recovery process for misdirected credit",
      "Correct beneficiary master data mapping if system error found",
      "Update CBS records post-resolution"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Daily Transfer Limit Issue",
    "investigation_steps": [
      "Check CBS/channel configuration for daily transfer limit applicable to the account/product",
      "Verify limit configuration against customer-requested/product-defined limit",
      "Review middleware log for limit-related decline response code"
    ],
    "next_best_actions": [
      "Correct limit configuration in CBS/channel management system",
      "Update records to reflect approved limit",
      "Communicate limit correction to middleware/payment gateway",
      "Verify limit change reflects correctly in subsequent transactions"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Transfer Limit Not Updated",
    "investigation_steps": [
      "Check pending limit change request status in channel management workflow",
      "Verify CBS approval/processing log for the limit update request",
      "Cross-check sync between CBS and middleware/payment gateway"
    ],
    "next_best_actions": [
      "Reprocess pending limit update request",
      "Escalate to IT/channel management team for sync issue",
      "Update CBS records to reflect correct limit",
      "Verify limit update takes effect"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "NEFT Transfer Failed",
    "investigation_steps": [
      "Check CBS NEFT transaction log and response code",
      "Verify RBI NEFT system (clearing) status for the transaction batch",
      "Review beneficiary bank IFSC/account validation log"
    ],
    "next_best_actions": [
      "Reverse debit if NEFT batch processing failed",
      "Resubmit transaction in next NEFT batch if technical failure confirmed",
      "Escalate to NEFT operations team for unresolved batch issue",
      "Update CBS records"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "RTGS Transfer Failed",
    "investigation_steps": [
      "Check CBS RTGS transaction log and response code",
      "Verify RBI RTGS system status for the transaction submission window",
      "Review beneficiary bank account/IFSC validation log"
    ],
    "next_best_actions": [
      "Reverse debit if RTGS transaction rejected",
      "Resubmit transaction if technical failure confirmed and within RTGS window",
      "Escalate to RTGS operations team for unresolved issue",
      "Update CBS records"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "IMPS Transfer Failed",
    "investigation_steps": [
      "Check CBS IMPS transaction log and response code",
      "Verify NPCI IMPS switch status for the transaction",
      "Review beneficiary bank response code for the transfer"
    ],
    "next_best_actions": [
      "Reverse debit if no credit confirmation received",
      "Raise tracer/inquiry via NPCI if applicable",
      "Escalate to IMPS operations team for unresolved issue",
      "Update CBS records and reconcile with settlement file"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "UPI Registration Failed",
    "investigation_steps": [
      "Check UPI app/PSP registration request log and response code",
      "Verify mobile number/bank account linkage validation with NPCI UPI switch",
      "Review SIM-binding/device verification log for the registration request"
    ],
    "next_best_actions": [
      "Retry UPI registration after correcting validation error",
      "Escalate to UPI/PSP/NPCI team if switch-level error confirmed",
      "Verify mobile number-bank account linkage",
      "Confirm successful registration post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "UPI ID Creation Failed",
    "investigation_steps": [
      "Check UPI ID creation request log at PSP/switch level",
      "Verify account linkage and bank validation response for VPA creation",
      "Review NPCI UPI switch response code for the request"
    ],
    "next_best_actions": [
      "Retry UPI ID creation request",
      "Escalate to PSP/NPCI team if switch-level error confirmed",
      "Correct account linkage if validation failure identified",
      "Verify UPI ID created successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "UPI PIN Reset Failed",
    "investigation_steps": [
      "Check UPI PIN reset request log and response code at PSP/switch level",
      "Verify card/account detail validation used for UPI PIN reset",
      "Review NPCI UPI switch log for the reset transaction"
    ],
    "next_best_actions": [
      "Retry UPI PIN reset request",
      "Escalate to PSP/NPCI team if switch-level error confirmed",
      "Correct card/account validation mapping if mismatch found",
      "Verify UPI PIN reset success post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "UPI Transaction Failed",
    "investigation_steps": [
      "Check NPCI UPI switch transaction log and response code",
      "Verify CBS authorization status for the linked account",
      "Review remitter/beneficiary bank response code for the transaction"
    ],
    "next_best_actions": [
      "Reverse debit if no credit confirmation received",
      "Raise dispute/tracer via NPCI UPI dispute management system if applicable",
      "Escalate to UPI operations team for unresolved issue",
      "Update CBS records and reconcile with settlement file"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "UPI Payment Pending",
    "investigation_steps": [
      "Check NPCI UPI switch transaction status for the payment",
      "Verify CBS hold/pending entry against the transaction reference",
      "Review beneficiary bank response status for the credit"
    ],
    "next_best_actions": [
      "Auto-reverse pending transaction post TAT if unresolved",
      "Update CBS to release hold/complete credit upon confirmation",
      "Reconcile with NPCI settlement file",
      "Escalate unresolved pending entries to UPI operations team"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "QR Code Payment Failed",
    "investigation_steps": [
      "Check QR code generation/scan log at app and switch level",
      "Verify NPCI UPI switch transaction status for the QR-initiated payment",
      "Review merchant/beneficiary response code for the transaction"
    ],
    "next_best_actions": [
      "Reverse debit if no credit confirmation received",
      "Retry QR payment processing if technical failure confirmed",
      "Escalate to UPI/QR service provider for switch-level error",
      "Update CBS records"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Merchant Payment Failed",
    "investigation_steps": [
      "Check payment gateway/switch transaction log for the merchant payment request",
      "Verify merchant account/QR/UPI handle validation status",
      "Review CBS authorization response for the transaction"
    ],
    "next_best_actions": [
      "Reverse debit if no merchant credit confirmation received",
      "Retry payment processing if technical failure confirmed",
      "Escalate to payment gateway/network team for unresolved issue",
      "Update CBS records"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Bill Payment Failed",
    "investigation_steps": [
      "Check biller aggregator/BBPS transaction log and response code",
      "Verify CBS authorization status for the bill payment debit",
      "Review biller-side confirmation status for the payment"
    ],
    "next_best_actions": [
      "Reverse debit if biller payment not confirmed",
      "Retry bill payment processing via aggregator",
      "Escalate to BBPS/biller aggregator team for unresolved transaction",
      "Update CBS records and reconcile with aggregator settlement file"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Credit Card Bill Payment Failed",
    "investigation_steps": [
      "Check card payment processing log and response code for the bill payment",
      "Verify CBS/card management system authorization status for the debit",
      "Review card network/processor confirmation status for credit to card account"
    ],
    "next_best_actions": [
      "Reverse debit if card account credit not confirmed",
      "Retry bill payment processing",
      "Escalate to card management/network team for unresolved transaction",
      "Update CBS/card system records and reconcile"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Loan EMI Payment Failed",
    "investigation_steps": [
      "Check loan management system log for EMI payment request status",
      "Verify CBS authorization status for the debit transaction",
      "Review loan account posting log for EMI credit confirmation"
    ],
    "next_best_actions": [
      "Reverse debit if EMI not credited to loan account",
      "Retry EMI payment processing",
      "Escalate to loan operations team for unresolved posting issue",
      "Update loan account records post-resolution"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Recharge Failed",
    "investigation_steps": [
      "Check recharge aggregator/BBPS transaction log and response code",
      "Verify CBS authorization status for the recharge debit",
      "Review telecom/DTH operator confirmation status for the recharge"
    ],
    "next_best_actions": [
      "Reverse debit if recharge not confirmed by operator",
      "Retry recharge processing via aggregator",
      "Escalate to aggregator team for unresolved transaction",
      "Update CBS records and reconcile with aggregator settlement file"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Utility Bill Payment Pending",
    "investigation_steps": [
      "Check BBPS/biller aggregator transaction status for the payment",
      "Verify CBS hold/pending entry against the transaction reference",
      "Review biller confirmation queue status"
    ],
    "next_best_actions": [
      "Monitor and update CBS upon biller confirmation",
      "Escalate to BBPS/aggregator team if delayed beyond cycle",
      "Reconcile with aggregator settlement file",
      "Release hold once payment is confirmed"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "AutoPay Registration Failed",
    "investigation_steps": [
      "Check UPI AutoPay/standing instruction registration request log at switch/PSP level",
      "Verify mandate creation/authorization response from NPCI",
      "Review CBS configuration for mandate registration support"
    ],
    "next_best_actions": [
      "Retry AutoPay/mandate registration request",
      "Escalate to PSP/NPCI team if switch-level error confirmed",
      "Correct CBS mandate configuration if required",
      "Verify mandate registered successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Standing Instruction Failed",
    "investigation_steps": [
      "Check CBS standing instruction execution log and error code",
      "Verify account balance/hold status at the scheduled execution time",
      "Review batch job processing log for standing instruction execution"
    ],
    "next_best_actions": [
      "Reprocess failed standing instruction execution",
      "Escalate to batch processing team if job failure confirmed",
      "Update CBS records post-execution",
      "Notify relevant teams of resolution status"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Auto-Debit Failed",
    "investigation_steps": [
      "Check CBS/mandate execution log for the auto-debit request",
      "Verify account balance and mandate validity at execution time",
      "Review NPCI/NACH mandate processing status for the transaction"
    ],
    "next_best_actions": [
      "Reprocess auto-debit if account balance/mandate validity confirmed",
      "Escalate to NACH/mandate processing team for unresolved failure",
      "Update CBS records post-resolution",
      "Reconcile with NACH settlement file"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Cheque Book Request Failed",
    "investigation_steps": [
      "Check CBS service request log for cheque book request status",
      "Verify request submission to cheque printing/dispatch vendor system",
      "Review API/middleware error code for the request"
    ],
    "next_best_actions": [
      "Retry cheque book request submission",
      "Escalate to vendor/operations team for printing/dispatch issue",
      "Update CBS service request status",
      "Verify request processed successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Cheque Stop Payment Failed",
    "investigation_steps": [
      "Check CBS stop payment request log and processing status",
      "Verify cheque details (number/date/amount) entered against CBS records",
      "Review request submission and confirmation log"
    ],
    "next_best_actions": [
      "Reprocess stop payment request immediately",
      "Escalate to operations team for urgent manual stop payment if time-critical",
      "Update CBS records to reflect stop payment status",
      "Verify stop payment is active and effective"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Fixed Deposit Opening Failed",
    "investigation_steps": [
      "Check CBS FD account opening request log and error code",
      "Verify account balance/debit status for the FD funding amount",
      "Review API/middleware error for the FD creation request"
    ],
    "next_best_actions": [
      "Retry FD opening request after correcting error",
      "Reverse any debit if FD account not created",
      "Escalate to deposits operations team for unresolved failure",
      "Verify FD account created successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Recurring Deposit Opening Failed",
    "investigation_steps": [
      "Check CBS RD account opening request log and error code",
      "Verify account balance/debit status for the RD funding amount",
      "Review API/middleware error for the RD creation request"
    ],
    "next_best_actions": [
      "Retry RD opening request after correcting error",
      "Reverse any debit if RD account not created",
      "Escalate to deposits operations team for unresolved failure",
      "Verify RD account created successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Loan Statement Download Failed",
    "investigation_steps": [
      "Check loan management system log for statement generation request status",
      "Verify document generation service/API response for the request",
      "Review app-side download/rendering log for the failure"
    ],
    "next_best_actions": [
      "Retry statement generation and download request",
      "Escalate to loan operations/IT team for document service failure",
      "Generate statement manually if automated process fails",
      "Verify successful download post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Account Statement Download Failed",
    "investigation_steps": [
      "Check CBS/statement generation service log for the request status",
      "Verify document generation API response code",
      "Review app-side download/rendering log for the failure"
    ],
    "next_best_actions": [
      "Retry statement generation and download request",
      "Escalate to IT team for document service failure",
      "Generate statement manually if automated process fails",
      "Verify successful download post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Interest Certificate Download Failed",
    "investigation_steps": [
      "Check CBS/certificate generation service log for the request status",
      "Verify document generation API response code for interest certificate",
      "Review app-side download/rendering log for the failure"
    ],
    "next_best_actions": [
      "Retry certificate generation and download request",
      "Escalate to IT/operations team for document service failure",
      "Generate certificate manually if automated process fails",
      "Verify successful download post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Tax Certificate Not Available",
    "investigation_steps": [
      "Check CBS/tax certificate generation batch job status for the relevant financial year",
      "Verify data completeness (TDS/interest computation) required for certificate generation",
      "Review document repository for certificate publication status"
    ],
    "next_best_actions": [
      "Trigger/reprocess certificate generation batch job",
      "Escalate to tax operations/IT team for data completeness issue",
      "Publish certificate to document repository post-generation",
      "Verify certificate availability post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Profile Update Failed",
    "investigation_steps": [
      "Check CBS profile update request log and error/response code",
      "Verify validation rules applied to the updated field",
      "Review workflow/approval queue status for the update request"
    ],
    "next_best_actions": [
      "Retry profile update after correcting validation error",
      "Escalate to middleware/CBS team for API-level error",
      "Process pending approval if stuck in workflow",
      "Verify profile update reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Registered Mobile Number Not Updated",
    "investigation_steps": [
      "Check CBS mobile number update request log and workflow status",
      "Verify OTP/authentication verification log for the update request",
      "Review approval/maker-checker queue status for the request"
    ],
    "next_best_actions": [
      "Expedite pending mobile number update request",
      "Escalate to operations team for workflow delay",
      "Update CBS records to reflect new mobile number",
      "Verify update reflects correctly across channels"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Email ID Not Updated",
    "investigation_steps": [
      "Check CBS email update request log and workflow status",
      "Verify verification log (email confirmation link/OTP) for the update request",
      "Review approval/maker-checker queue status for the request"
    ],
    "next_best_actions": [
      "Expedite pending email update request",
      "Escalate to operations team for workflow delay",
      "Update CBS records to reflect new email ID",
      "Verify update reflects correctly across channels"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Address Update Pending",
    "investigation_steps": [
      "Check CBS address update request log and workflow/approval status",
      "Verify supporting document verification status if required",
      "Review maker-checker queue for pending approval"
    ],
    "next_best_actions": [
      "Expedite pending address update approval",
      "Escalate to operations team for workflow delay",
      "Update CBS records post-approval",
      "Verify update reflects correctly in customer profile"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "PAN Update Failed",
    "investigation_steps": [
      "Check CBS PAN update request log and validation response",
      "Verify PAN format/NSDL-IT department validation API response",
      "Review workflow/approval queue status for the update request"
    ],
    "next_best_actions": [
      "Retry PAN update after correcting validation error",
      "Escalate to compliance/operations team for validation API failure",
      "Process pending approval if stuck in workflow",
      "Verify PAN update reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Nominee Update Failed",
    "investigation_steps": [
      "Check CBS nominee update request log and workflow status",
      "Verify nominee detail validation (KYC/relationship/age) against submitted request",
      "Review maker-checker approval queue status"
    ],
    "next_best_actions": [
      "Retry nominee update after correcting validation error",
      "Escalate to operations team for workflow delay",
      "Process pending approval",
      "Verify nominee details updated correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "KYC Verification Pending",
    "investigation_steps": [
      "Check KYC verification workflow status and document validation queue",
      "Verify source verification (Aadhaar/PAN/CKYC) API response status",
      "Review maker-checker approval queue for pending KYC verification"
    ],
    "next_best_actions": [
      "Expedite pending KYC verification processing",
      "Escalate to KYC/compliance operations team for backlog",
      "Update CBS KYC status post-verification",
      "Verify customer channel access restored if KYC was blocking"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "KYC Update Failed",
    "investigation_steps": [
      "Check CBS KYC update request log and error/response code",
      "Verify document upload and validation service log",
      "Review CKYC/source verification API response for the update"
    ],
    "next_best_actions": [
      "Retry KYC update after correcting validation error",
      "Escalate to compliance/IT team for API-level failure",
      "Reprocess document verification if upload failed",
      "Verify KYC update reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Video KYC Failed",
    "investigation_steps": [
      "Check video KYC application/vendor session log for failure point",
      "Verify liveness detection and document capture module response",
      "Review network/bandwidth log during the video KYC session"
    ],
    "next_best_actions": [
      "Reschedule video KYC session for the customer",
      "Escalate to video KYC vendor for module-level failure",
      "Advise alternate KYC verification method if repeated failure",
      "Verify successful KYC completion post-retry"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "SMS Alerts Not Received",
    "investigation_steps": [
      "Check SMS gateway delivery log for the alert",
      "Verify registered mobile number and alert subscription status in CBS",
      "Review alert trigger log at CBS/middleware level"
    ],
    "next_best_actions": [
      "Resend the missed alert SMS",
      "Correct mobile number/subscription mapping if found incorrect",
      "Escalate to SMS gateway vendor if delivery failure confirmed",
      "Verify alert delivery post-correction"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Push Notifications Not Received",
    "investigation_steps": [
      "Check push notification service (FCM/APNs) delivery log for the alert",
      "Verify device token registration status in notification service",
      "Review app notification permission/settings status on device"
    ],
    "next_best_actions": [
      "Re-register device token with notification service",
      "Resend the missed push notification",
      "Escalate to mobile app/notification vendor team if delivery failure confirmed",
      "Verify notification delivery post-correction"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Email Alerts Not Received",
    "investigation_steps": [
      "Check email gateway/SMTP delivery log for the alert",
      "Verify registered email ID and alert subscription status in CBS",
      "Review spam/bounce-back log for the email delivery attempt"
    ],
    "next_best_actions": [
      "Resend the missed email alert",
      "Correct email ID/subscription mapping if found incorrect",
      "Escalate to email gateway vendor if delivery failure confirmed",
      "Verify alert delivery post-correction"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Security Alerts Not Received",
    "investigation_steps": [
      "Check security alert trigger log at CBS/fraud monitoring system",
      "Verify delivery channel (SMS/email/push) gateway log for the alert",
      "Review registered contact details and subscription status"
    ],
    "next_best_actions": [
      "Resend the missed security alert through available channel",
      "Correct contact details/subscription mapping if found incorrect",
      "Escalate to relevant gateway vendor if delivery failure confirmed",
      "Verify alert delivery post-correction"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Unauthorized Login Attempt",
    "investigation_steps": [
      "Check authentication server log for the login attempt details (IP, device, timestamp)",
      "Verify fraud monitoring system alerts for anomalous login pattern",
      "Review device binding and geolocation log for the session"
    ],
    "next_best_actions": [
      "Block/restrict account access as precaution",
      "Force password/MPIN reset for the account",
      "Escalate to fraud/security investigation team",
      "Notify customer of the security event through verified channel"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Unauthorized Transaction",
    "investigation_steps": [
      "Check CBS/payment gateway transaction log for the disputed transaction",
      "Verify device/session/authentication log used for the transaction",
      "Review fraud monitoring system alerts for the account",
      "Cross-check transaction geolocation/velocity anomaly indicators"
    ],
    "next_best_actions": [
      "Block account/channel access immediately if not already done",
      "Raise dispute/chargeback through applicable network if required",
      "Provisionally credit account per RBI liability guidelines pending investigation",
      "Escalate to fraud investigation team"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Fraudulent Transaction",
    "investigation_steps": [
      "Review fraud monitoring system flags for the transaction",
      "Check authentication/session log for compromise indicators (phishing/SIM-swap/malware)",
      "Cross-check NPCI/network fraud advisory for the BIN/account",
      "Verify device binding history for anomalous device change"
    ],
    "next_best_actions": [
      "Block account/channel access and freeze further suspicious transactions",
      "Initiate dispute/chargeback process",
      "Escalate to fraud risk and law enforcement",
      "Process provisional credit as per regulatory timelines pending investigation outcome"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Account Access Blocked",
    "investigation_steps": [
      "Check CBS/channel account status flag for block reason and trigger event",
      "Verify fraud monitoring/risk system log for the block trigger",
      "Review block request history (customer-initiated/system-triggered)"
    ],
    "next_best_actions": [
      "Unblock account post identity verification if block found unwarranted",
      "Escalate to fraud/risk team if block was security-triggered and requires further review",
      "Update CBS access status records",
      "Verify account access restored with test login"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Suspicious Login Detected",
    "investigation_steps": [
      "Check fraud monitoring system log for the flagged login anomaly",
      "Verify device/geolocation/IP reputation data for the session",
      "Review authentication factor log used for the login"
    ],
    "next_best_actions": [
      "Restrict session/account access as precaution pending verification",
      "Trigger additional authentication/verification step for the customer",
      "Escalate to fraud/security team for investigation",
      "Restore access post successful verification"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Device Change Verification Failed",
    "investigation_steps": [
      "Check device change request log and verification workflow status",
      "Verify OTP/authentication factor log used for the new device verification",
      "Review device binding history for the account"
    ],
    "next_best_actions": [
      "Retry device change verification process",
      "Escalate to security team if verification logic error confirmed",
      "Manually verify and approve device change if customer identity confirmed through alternate channel",
      "Update device binding records post-verification"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "App Update Failed",
    "investigation_steps": [
      "Check app store/distribution platform download and installation log",
      "Verify device compatibility (OS version, storage) for the update",
      "Review app update package integrity/signing certificate status"
    ],
    "next_best_actions": [
      "Advise alternate update method (manual download/reinstall) if platform-level issue",
      "Escalate to mobile app development team for package/compatibility issue",
      "Re-publish corrected update package if defect confirmed",
      "Verify successful update post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "App Update Caused Login Issue",
    "investigation_steps": [
      "Check crash/error log specific to the updated app version for login module",
      "Verify backward compatibility of login API with the new app version",
      "Review session/token handling changes introduced in the update"
    ],
    "next_best_actions": [
      "Escalate to mobile app development team for urgent hotfix",
      "Roll back problematic update if critical login defect confirmed",
      "Issue patch release addressing the login issue",
      "Verify login functionality post-fix across affected versions"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Feature Missing After Update",
    "investigation_steps": [
      "Check release notes/deployment log for the affected feature in the new version",
      "Verify feature flag/configuration toggle status post-update",
      "Review app build log for missing module/component in the release package"
    ],
    "next_best_actions": [
      "Enable feature flag/configuration if inadvertently disabled",
      "Escalate to development team for missing component in build",
      "Issue corrective patch release if feature genuinely omitted",
      "Verify feature availability post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Dark Mode Display Issue",
    "investigation_steps": [
      "Check UI rendering log for dark mode theme module errors",
      "Verify device OS-level dark mode compatibility with app version",
      "Review theme configuration/asset loading log for the affected screens"
    ],
    "next_best_actions": [
      "Escalate to app development team for theme rendering fix",
      "Issue patch release correcting dark mode display defects",
      "Advise toggling theme setting as interim workaround",
      "Verify display fix across affected screens post-update"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Language Change Not Working",
    "investigation_steps": [
      "Check application language module configuration log",
      "Verify language pack/resource file loading status for the selected language",
      "Review software version/patch log for the language module"
    ],
    "next_best_actions": [
      "Escalate to vendor/application team for software fix",
      "Reconfigure language module settings",
      "Schedule software patch deployment",
      "Verify fix with test selection in affected language"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Complaint Registration Failed",
    "investigation_steps": [
      "Check complaint management system log for registration request status",
      "Verify API/middleware error code for the submission failure",
      "Review form validation log for the complaint submission"
    ],
    "next_best_actions": [
      "Retry complaint registration after correcting validation error",
      "Escalate to IT/middleware team for API-level failure",
      "Manually register the complaint if system issue persists",
      "Confirm complaint registered successfully with reference number"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Complaint Status Not Updated",
    "investigation_steps": [
      "Check complaint management system log for status update processing",
      "Verify workflow/case management system sync with customer-facing status display",
      "Review case investigation log for actual resolution stage"
    ],
    "next_best_actions": [
      "Update complaint status to reflect actual investigation stage",
      "Escalate to IT team for sync issue between systems",
      "Reconcile case status across all touchpoints",
      "Verify status displays correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Service Request Not Submitted",
    "investigation_steps": [
      "Check service request module log for submission request status",
      "Verify API/middleware error code for the submission failure",
      "Review form validation log for the request submission"
    ],
    "next_best_actions": [
      "Retry service request submission after correcting validation error",
      "Escalate to IT/middleware team for API-level failure",
      "Manually log the service request if system issue persists",
      "Confirm request submitted successfully with reference number"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Service Request Status Not Updated",
    "investigation_steps": [
      "Check service request management system log for status update processing",
      "Verify workflow sync with customer-facing status display",
      "Review fulfilment/processing log for actual request stage"
    ],
    "next_best_actions": [
      "Update service request status to reflect actual processing stage",
      "Escalate to IT team for sync issue between systems",
      "Reconcile status across all touchpoints",
      "Verify status displays correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Feedback Submission Failed",
    "investigation_steps": [
      "Check feedback module log for submission request status",
      "Verify API/middleware error code for the submission failure",
      "Review form validation log for the feedback submission"
    ],
    "next_best_actions": [
      "Retry feedback submission after correcting validation error",
      "Escalate to IT/middleware team for API-level failure",
      "Manually log the feedback if system issue persists",
      "Confirm feedback submitted successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Digital Token Not Generated",
    "investigation_steps": [
      "Check token generation service/HSM log for the request status",
      "Verify CBS/channel configuration for digital token issuance eligibility",
      "Review API/middleware error code for the generation request"
    ],
    "next_best_actions": [
      "Retry digital token generation request",
      "Escalate to HSM/security team for cryptographic failure",
      "Correct eligibility/configuration mapping if found incorrect",
      "Verify token generated successfully post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Card Management Feature Not Working",
    "investigation_steps": [
      "Check card management module API log (block/unblock/limit-set) for error response",
      "Verify card management system connectivity with CBS/card network",
      "Review app-side rendering log for the card management screen"
    ],
    "next_best_actions": [
      "Escalate to card management system/middleware team for API failure",
      "Retry card management action processing",
      "Escalate to app team for rendering-level fix",
      "Verify feature functions correctly post-fix"
    ]
  },
  {
    "major_issue": "Mobile Banking",
    "sub_issue": "Mobile Banking Deactivation Failed",
    "investigation_steps": [
      "Check CBS/channel deactivation request log and processing status",
      "Verify workflow/approval queue status for the deactivation request",
      "Review dependency check (pending transactions/mandates) blocking deactivation"
    ],
    "next_best_actions": [
      "Retry deactivation after clearing blocking dependency",
      "Escalate to operations/IT team for workflow delay",
      "Update CBS channel status records post-deactivation",
      "Verify channel access deactivated successfully post-fix"
    ]
  }
],
[
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Application Rejected",
    "investigation_steps": [
      "Check Loan Origination System (LOS) log for rejection reason/score code",
      "Verify credit bureau score and policy rule engine output used for the decision",
      "Review income/eligibility documents submitted against credit policy criteria",
      "Cross-check underwriter remarks in the application file"
    ],
    "next_best_actions": [
      "Communicate rejection reason code internally for record",
      "Re-evaluate application if documentation/data error identified",
      "Escalate to credit policy team if rule engine misfire confirmed",
      "Update LOS application status with final decision rationale"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Application Pending",
    "investigation_steps": [
      "Check LOS workflow stage and queue assignment for the application",
      "Verify pending document/verification checklist status",
      "Review underwriter/credit team action log for delay"
    ],
    "next_best_actions": [
      "Reassign application for expedited processing",
      "Follow up on pending document/verification requirement",
      "Escalate to credit operations team if stuck beyond TAT",
      "Update LOS status post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Approval Delayed",
    "investigation_steps": [
      "Check LOS approval workflow stage and approver queue status",
      "Verify credit underwriting completion timestamp versus approval TAT",
      "Review pending sanction committee/approval authority action log"
    ],
    "next_best_actions": [
      "Expedite pending approval action with relevant authority",
      "Escalate to credit operations team for TAT breach",
      "Update LOS workflow status post-approval",
      "Communicate revised timeline internally for tracking"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Approval Rejected Without Reason",
    "investigation_steps": [
      "Check LOS decision log for rejection reason code captured at approval stage",
      "Verify underwriter/credit committee remarks against system-generated decision",
      "Review policy rule engine output for the application"
    ],
    "next_best_actions": [
      "Document and record proper rejection reason in LOS",
      "Escalate to credit policy team for review if reason code missing/incomplete",
      "Correct LOS configuration to mandate reason capture",
      "Update application file with documented rationale"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Processing Delay",
    "investigation_steps": [
      "Check LOS workflow stage-wise timestamp log for the application",
      "Verify bottleneck stage (document collection/verification/underwriting/sanction)",
      "Review TAT compliance report for the loan product"
    ],
    "next_best_actions": [
      "Reassign application to expedite bottleneck stage",
      "Escalate to operations team for process delay resolution",
      "Update LOS workflow status",
      "Review process for recurring bottleneck and report for correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Verification Pending",
    "investigation_steps": [
      "Check verification agency (field/telephonic/document) assignment and status log",
      "Verify verification report submission timestamp versus TAT",
      "Review LOS queue for pending verification stage"
    ],
    "next_best_actions": [
      "Follow up with verification agency for pending report",
      "Escalate to operations team if verification delayed beyond TAT",
      "Update LOS status upon verification completion",
      "Reassign verification if agency non-responsive"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Document Verification Delay",
    "investigation_steps": [
      "Check document verification queue and assigned reviewer log",
      "Verify document completeness checklist status against submitted documents",
      "Review TAT compliance for document verification stage"
    ],
    "next_best_actions": [
      "Expedite pending document verification",
      "Escalate to credit operations team for backlog clearance",
      "Request missing/additional documents if incomplete",
      "Update LOS status post-verification"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Document Rejected",
    "investigation_steps": [
      "Check document rejection reason code in LOS",
      "Verify document authenticity/validation log (income proof, KYC, property documents)",
      "Review policy checklist against rejected document type"
    ],
    "next_best_actions": [
      "Communicate specific document deficiency for resubmission",
      "Re-verify document if rejection found erroneous",
      "Escalate to credit policy team if validation rule misfire confirmed",
      "Update LOS document status post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Agreement Not Received",
    "investigation_steps": [
      "Check LOS/document generation log for loan agreement creation status",
      "Verify dispatch/courier log for the agreement document",
      "Review digital agreement (e-sign/e-stamp) delivery log if applicable"
    ],
    "next_best_actions": [
      "Regenerate and dispatch loan agreement",
      "Escalate to documentation team for generation failure",
      "Re-trigger e-sign/e-stamp workflow if digital process failed",
      "Confirm receipt and update LOS records"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Sanction Letter Not Received",
    "investigation_steps": [
      "Check LOS sanction letter generation log and timestamp",
      "Verify dispatch/email/SMS delivery log for the sanction letter",
      "Review document template/generation service error log if applicable"
    ],
    "next_best_actions": [
      "Regenerate and resend sanction letter through available channel",
      "Escalate to documentation/IT team for generation failure",
      "Confirm receipt and update LOS records",
      "Provide duplicate copy if required"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Disbursement Delayed",
    "investigation_steps": [
      "Check LOS/LMS disbursement workflow stage and pending approval log",
      "Verify disbursement request submission timestamp versus TAT",
      "Review pending condition (document/collateral/insurance) blocking disbursement"
    ],
    "next_best_actions": [
      "Expedite pending disbursement approval/condition clearance",
      "Escalate to credit operations team for TAT breach",
      "Process disbursement immediately upon condition fulfilment",
      "Update LMS records post-disbursement"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Disbursement Failed",
    "investigation_steps": [
      "Check CBS/payment processing log for the disbursement transaction status",
      "Verify beneficiary account validation log for the disbursement request",
      "Review LMS disbursement request error/response code"
    ],
    "next_best_actions": [
      "Retry disbursement processing after correcting error",
      "Escalate to payments/operations team for unresolved failure",
      "Update LMS and CBS records post-resolution",
      "Confirm successful credit to customer account"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Partial Loan Disbursement",
    "investigation_steps": [
      "Check LMS disbursement schedule (tranche-based) against sanctioned amount",
      "Verify condition fulfilment status for remaining tranche release",
      "Review CBS credit entries against total disbursed amount"
    ],
    "next_best_actions": [
      "Process remaining tranche upon condition fulfilment",
      "Update LMS records to reflect disbursement schedule status",
      "Escalate to credit operations team if tranche release delayed",
      "Communicate disbursement schedule status internally"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Incorrect Loan Amount Disbursed",
    "investigation_steps": [
      "Check LMS disbursement request amount against sanctioned loan amount",
      "Verify CBS credit entry for the actual disbursed amount",
      "Review disbursement instruction/data entry log for discrepancy"
    ],
    "next_best_actions": [
      "Correct disbursement amount via additional credit or recovery as applicable",
      "Update LMS and CBS records to reflect correct amount",
      "Escalate to operations team for data entry error correction",
      "Reconcile loan account post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Disbursed to Wrong Account",
    "investigation_steps": [
      "Check LMS disbursement instruction for the account number entered",
      "Verify CBS credit entry against the intended beneficiary account",
      "Review data entry/account validation log for the disbursement request"
    ],
    "next_best_actions": [
      "Initiate recovery/reversal from the incorrectly credited account",
      "Re-disburse to correct account upon recovery",
      "Escalate to operations team for data entry error correction",
      "Update LMS and CBS records post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Disbursement Pending",
    "investigation_steps": [
      "Check LMS disbursement queue status and pending workflow stage",
      "Verify condition/document fulfilment status blocking disbursement",
      "Review CBS for any provisional hold entry"
    ],
    "next_best_actions": [
      "Process disbursement upon condition fulfilment",
      "Escalate to credit operations team for unresolved pending status",
      "Update LMS records post-disbursement",
      "Communicate status to relevant internal teams"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Disbursement Reversed",
    "investigation_steps": [
      "Check CBS reversal entry against original disbursement transaction",
      "Verify LMS log for reversal trigger reason",
      "Review beneficiary account status at the time of reversal"
    ],
    "next_best_actions": [
      "Correct reversal entry if found erroneous and re-disburse",
      "Update LMS and CBS records",
      "Escalate to operations team for reversal root cause",
      "Reconcile loan account post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Top-up Loan Disbursement Delay",
    "investigation_steps": [
      "Check LOS/LMS top-up loan application workflow stage",
      "Verify existing loan account eligibility and outstanding balance check for top-up",
      "Review pending approval/condition status for top-up disbursement"
    ],
    "next_best_actions": [
      "Expedite pending top-up approval/condition clearance",
      "Escalate to credit operations team for TAT breach",
      "Process top-up disbursement upon fulfilment",
      "Update LMS records post-disbursement"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Cancellation Not Processed",
    "investigation_steps": [
      "Check LOS/LMS cancellation request log and processing status",
      "Verify workflow/approval queue status for the cancellation request",
      "Review dependency (disbursed amount/charges) blocking cancellation"
    ],
    "next_best_actions": [
      "Process pending cancellation request",
      "Escalate to operations team for workflow delay",
      "Reverse any charges/disbursement as applicable upon cancellation",
      "Update LOS/LMS records post-cancellation"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Cancellation Request Rejected",
    "investigation_steps": [
      "Check LOS/LMS cancellation request rejection reason log",
      "Verify policy/eligibility criteria applied for the rejection decision",
      "Review disbursement status at the time of cancellation request"
    ],
    "next_best_actions": [
      "Re-evaluate cancellation request if rejection found erroneous",
      "Escalate to credit policy team for policy clarification",
      "Communicate documented rejection rationale",
      "Update LOS/LMS records with final decision"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Paid but Showing Due",
    "investigation_steps": [
      "Check LMS EMI posting log against payment confirmation in CBS/payment gateway",
      "Verify batch/real-time posting job status for the EMI payment",
      "Cross-check NACH/auto-debit settlement file for the payment entry"
    ],
    "next_best_actions": [
      "Manually post the EMI payment to update due status",
      "Escalate to LMS/batch processing team if posting job failure confirmed",
      "Reconcile with settlement file",
      "Verify EMI status reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Deducted Twice",
    "investigation_steps": [
      "Check CBS/NACH debit log for duplicate EMI debit entries",
      "Verify LMS EMI schedule against actual debit count for the period",
      "Cross-check mandate execution log for retry/duplicate submission"
    ],
    "next_best_actions": [
      "Reverse the duplicate EMI debit",
      "Update LMS and CBS records",
      "Escalate to NACH/mandate processing team to prevent recurrence",
      "Reconcile loan account post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Auto-Debit Failed",
    "investigation_steps": [
      "Check NACH/mandate execution log for the EMI debit request",
      "Verify account balance and mandate validity at execution time",
      "Review LMS EMI due date versus mandate presentation date"
    ],
    "next_best_actions": [
      "Reprocess auto-debit if account balance/mandate validity confirmed",
      "Escalate to NACH/mandate processing team for unresolved failure",
      "Update LMS records post-resolution",
      "Advise alternate payment if mandate-level issue persists"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Debited Before Due Date",
    "investigation_steps": [
      "Check NACH mandate presentation date log against configured EMI due date",
      "Verify LMS EMI schedule configuration for the due date",
      "Review mandate registration parameters for presentation date mismatch"
    ],
    "next_best_actions": [
      "Correct mandate presentation date configuration",
      "Refund/adjust if early debit caused financial inconvenience as per policy",
      "Escalate to LMS/NACH team for configuration fix",
      "Verify subsequent EMI debits occur on correct date"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Debited After Due Date",
    "investigation_steps": [
      "Check NACH mandate presentation date log against configured EMI due date",
      "Verify LMS EMI schedule configuration and mandate execution timestamp",
      "Review penal interest/late fee trigger log linked to the delayed debit"
    ],
    "next_best_actions": [
      "Correct mandate presentation date configuration",
      "Reverse any penal interest/late fee incorrectly charged due to processing delay",
      "Escalate to LMS/NACH team for configuration fix",
      "Verify subsequent EMI debits occur on correct date"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Not Updated",
    "investigation_steps": [
      "Check LMS EMI posting log for the payment transaction",
      "Verify CBS/payment gateway confirmation against LMS posting status",
      "Cross-check batch job execution log for EMI update process"
    ],
    "next_best_actions": [
      "Manually post the EMI update",
      "Escalate to LMS/batch processing team if job failure confirmed",
      "Reconcile loan account records",
      "Verify EMI status updates correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Payment Failed",
    "investigation_steps": [
      "Check payment gateway/NACH transaction log and response code",
      "Verify CBS authorization status for the EMI debit",
      "Review LMS posting log for the failed payment attempt"
    ],
    "next_best_actions": [
      "Reverse any debit without successful EMI posting",
      "Retry EMI payment processing",
      "Escalate to payments/NACH team for unresolved failure",
      "Update LMS records post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Payment Pending",
    "investigation_steps": [
      "Check payment gateway/NACH transaction status in processing queue",
      "Verify LMS hold/pending entry against the EMI payment",
      "Review settlement file for matching entry"
    ],
    "next_best_actions": [
      "Monitor and update LMS upon payment confirmation",
      "Escalate to payments/NACH team if delayed beyond cycle",
      "Reconcile with settlement file",
      "Release hold once payment is confirmed"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Payment Reversed",
    "investigation_steps": [
      "Check CBS/LMS reversal entry against the original EMI payment record",
      "Verify payment gateway/NACH reversal message log",
      "Review reversal trigger reason (insufficient funds/mandate failure/dispute)"
    ],
    "next_best_actions": [
      "Correct reversal entry in LMS if found erroneous",
      "Re-process EMI payment if reversal found incorrect",
      "Reconcile loan account post-correction",
      "Escalate to payments team if reversal message error identified"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Schedule Incorrect",
    "investigation_steps": [
      "Check LMS amortization schedule generation log against sanctioned loan terms",
      "Verify interest rate, tenure, and principal configuration used for schedule generation",
      "Review any rate reset/restructuring event affecting the schedule"
    ],
    "next_best_actions": [
      "Regenerate corrected EMI schedule based on accurate loan parameters",
      "Update LMS records with corrected schedule",
      "Escalate to LMS/credit operations team for configuration error",
      "Communicate revised schedule for the account"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Incorrect EMI Amount",
    "investigation_steps": [
      "Check LMS EMI calculation against sanctioned principal, interest rate, and tenure",
      "Verify interest rate reset history applied to the calculation",
      "Review any manual override/adjustment entry in LMS"
    ],
    "next_best_actions": [
      "Recalculate and correct EMI amount in LMS",
      "Update mandate/NACH amount if registered amount mismatches",
      "Escalate to LMS team for calculation engine error",
      "Communicate corrected EMI amount and revised schedule"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Increased Without Notice",
    "investigation_steps": [
      "Check LMS interest rate reset log and trigger event (floating rate change/tenure adjustment)",
      "Verify customer communication/notice dispatch log for the EMI revision",
      "Review policy requirement for prior notice period before EMI change"
    ],
    "next_best_actions": [
      "Issue revised EMI notice with effective date and reason",
      "Escalate to LMS/communication team if notice dispatch failure confirmed",
      "Reassess EMI revision timeline for policy compliance",
      "Update customer communication records"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "EMI Reduction Not Applied",
    "investigation_steps": [
      "Check LMS interest rate reset/restructuring approval log for the EMI reduction trigger",
      "Verify pending workflow status for applying the reduction",
      "Review batch job log responsible for EMI schedule update"
    ],
    "next_best_actions": [
      "Apply pending EMI reduction to the account",
      "Escalate to LMS/batch processing team for workflow delay",
      "Update LMS records with corrected EMI",
      "Verify revised EMI reflects correctly in subsequent cycle"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Tenure Incorrect",
    "investigation_steps": [
      "Check LMS loan account configuration against sanctioned tenure",
      "Verify any restructuring/rescheduling event affecting tenure",
      "Review data entry log at loan account setup stage"
    ],
    "next_best_actions": [
      "Correct tenure configuration in LMS",
      "Regenerate amortization schedule based on corrected tenure",
      "Escalate to operations team for data entry error",
      "Communicate corrected tenure and revised schedule"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Outstanding Balance Incorrect",
    "investigation_steps": [
      "Check LMS ledger posting log for all credits/debits against the loan account",
      "Verify EMI, prepayment, and charge postings for completeness and accuracy",
      "Cross-check interest accrual calculation against outstanding principal"
    ],
    "next_best_actions": [
      "Recalculate and correct outstanding balance in LMS",
      "Escalate to LMS/accounts team for posting/calculation error",
      "Update loan account records post-correction",
      "Communicate corrected outstanding balance"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Interest Charged Incorrectly",
    "investigation_steps": [
      "Check LMS interest accrual calculation against sanctioned rate and applicable rate reset history",
      "Verify interest computation method (reducing/flat balance) configuration",
      "Review any manual override entry affecting interest calculation"
    ],
    "next_best_actions": [
      "Recalculate and correct interest charged",
      "Reverse excess interest if overcharged",
      "Escalate to LMS team for calculation engine error",
      "Update loan account records post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Excess Interest Charged",
    "investigation_steps": [
      "Check LMS interest accrual log against approved rate and computation method",
      "Verify rate reset history and effective date application",
      "Review any duplicate/erroneous interest posting entry"
    ],
    "next_best_actions": [
      "Reverse excess interest charged",
      "Recalculate correct interest and update LMS records",
      "Escalate to LMS team for calculation error root cause",
      "Communicate correction and revised statement to relevant teams"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Floating Interest Rate Not Updated",
    "investigation_steps": [
      "Check benchmark rate (repo/MCLR) change log against LMS configured rate",
      "Verify rate reset trigger and effective date logic in LMS",
      "Review batch job log responsible for periodic rate update"
    ],
    "next_best_actions": [
      "Apply pending rate update to the loan account",
      "Escalate to LMS/treasury team for rate update workflow delay",
      "Regenerate revised EMI schedule post-update",
      "Verify rate reflects correctly going forward"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Interest Certificate Not Issued",
    "investigation_steps": [
      "Check LMS/certificate generation batch job status for the relevant financial year",
      "Verify data completeness required for interest certificate generation",
      "Review document repository for certificate publication status"
    ],
    "next_best_actions": [
      "Trigger/reprocess certificate generation batch job",
      "Escalate to operations/IT team for data completeness issue",
      "Publish certificate to document repository post-generation",
      "Verify certificate availability post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Statement Not Available",
    "investigation_steps": [
      "Check LMS/statement generation service log for the request status",
      "Verify document generation API/batch job response code",
      "Review document repository for statement publication status"
    ],
    "next_best_actions": [
      "Retry statement generation and publication",
      "Escalate to IT/operations team for document service failure",
      "Generate statement manually if automated process fails",
      "Verify successful availability post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Statement Incorrect",
    "investigation_steps": [
      "Compare statement data against LMS source ledger for the loan account",
      "Verify statement generation template/data mapping logic",
      "Cross-check transaction entries reflected versus actual postings"
    ],
    "next_best_actions": [
      "Correct statement data/template mapping",
      "Regenerate corrected statement",
      "Escalate to IT team for module-level fix if systemic error found",
      "Verify corrected statement accuracy post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Repayment Schedule Not Received",
    "investigation_steps": [
      "Check LMS repayment schedule generation log and dispatch status",
      "Verify email/SMS/document delivery log for the schedule",
      "Review document generation service error log if applicable"
    ],
    "next_best_actions": [
      "Regenerate and resend repayment schedule",
      "Escalate to documentation/IT team for generation/dispatch failure",
      "Confirm receipt and update LMS records",
      "Provide duplicate copy if required"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Repayment Schedule Incorrect",
    "investigation_steps": [
      "Check LMS amortization schedule generation log against sanctioned loan terms",
      "Verify interest rate, tenure, and principal configuration used",
      "Review any rate reset/restructuring event affecting the schedule"
    ],
    "next_best_actions": [
      "Regenerate corrected repayment schedule",
      "Update LMS records with corrected schedule",
      "Escalate to LMS team for configuration/calculation error",
      "Communicate revised schedule for the account"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Foreclosure Request Pending",
    "investigation_steps": [
      "Check LMS foreclosure request workflow stage and pending approval log",
      "Verify foreclosure quote generation status against outstanding balance",
      "Review payment confirmation log for the foreclosure amount"
    ],
    "next_best_actions": [
      "Expedite pending foreclosure processing",
      "Generate and issue foreclosure quote if pending",
      "Escalate to credit operations team for workflow delay",
      "Process closure upon payment confirmation"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Foreclosure Not Processed",
    "investigation_steps": [
      "Check LMS foreclosure payment confirmation log against request",
      "Verify outstanding balance computation used for foreclosure",
      "Review workflow/approval queue status for closure processing"
    ],
    "next_best_actions": [
      "Process foreclosure closure upon verified payment confirmation",
      "Escalate to operations team for processing delay",
      "Update LMS records to reflect closed status",
      "Issue closure confirmation/NOC to relevant records"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Foreclosure Charges Incorrect",
    "investigation_steps": [
      "Check LMS foreclosure charge calculation against applicable policy/RBI guidelines (fixed vs floating rate loans)",
      "Verify charge computation method and rate applied",
      "Review any waiver/exemption eligibility for the account"
    ],
    "next_best_actions": [
      "Recalculate and correct foreclosure charges",
      "Refund excess charges if overcharged",
      "Escalate to LMS/policy team for calculation engine error",
      "Update loan account records post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Prepayment Not Updated",
    "investigation_steps": [
      "Check LMS posting log for the prepayment transaction",
      "Verify payment confirmation in CBS/payment gateway against LMS posting status",
      "Cross-check batch job execution log for prepayment update process"
    ],
    "next_best_actions": [
      "Manually post the prepayment update",
      "Escalate to LMS/batch processing team if job failure confirmed",
      "Recalculate outstanding balance and EMI/tenure impact",
      "Verify prepayment reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Prepayment Penalty Dispute",
    "investigation_steps": [
      "Check LMS prepayment penalty calculation against applicable policy/RBI guidelines and loan agreement terms",
      "Verify floating vs fixed rate classification for penalty applicability",
      "Review any waiver/exemption eligibility for the account"
    ],
    "next_best_actions": [
      "Recalculate and correct penalty if misapplied",
      "Refund penalty if found non-applicable per regulatory guideline",
      "Escalate to credit policy team for review",
      "Update loan account records post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Part Payment Not Updated",
    "investigation_steps": [
      "Check LMS posting log for the part payment transaction",
      "Verify payment confirmation in CBS/payment gateway against LMS posting status",
      "Cross-check batch job execution log for part payment update process"
    ],
    "next_best_actions": [
      "Manually post the part payment update",
      "Escalate to LMS/batch processing team if job failure confirmed",
      "Recalculate outstanding balance and revised schedule",
      "Verify part payment reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Part Payment Rejected",
    "investigation_steps": [
      "Check LMS part payment request rejection reason code",
      "Verify policy eligibility (minimum amount/frequency/lock-in period) for part payment",
      "Review payment processing log for technical rejection"
    ],
    "next_best_actions": [
      "Reprocess part payment if rejection found erroneous",
      "Communicate policy-based rejection rationale if applicable",
      "Escalate to LMS team for technical rejection root cause",
      "Update LMS records post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Closure Not Updated",
    "investigation_steps": [
      "Check LMS closure processing log against final payment confirmation",
      "Verify batch job/workflow status for closure status update",
      "Cross-check CBS/LMS sync for the account status field"
    ],
    "next_best_actions": [
      "Manually update closure status in LMS",
      "Escalate to IT/batch processing team for sync issue",
      "Issue closure confirmation post-update",
      "Verify status reflects correctly across systems"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Account Still Showing Active",
    "investigation_steps": [
      "Check LMS account status flag against final settlement/closure confirmation",
      "Verify batch job/sync process responsible for status update",
      "Cross-check CBS/credit bureau reporting feed for status mismatch"
    ],
    "next_best_actions": [
      "Manually correct account status to closed in LMS",
      "Escalate to IT team for batch/sync job failure",
      "Update downstream systems (CBS, credit bureau feed) accordingly",
      "Verify status reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Closure Delay",
    "investigation_steps": [
      "Check LMS closure workflow stage and pending approval/verification log",
      "Verify final payment/foreclosure confirmation timestamp versus closure TAT",
      "Review pending document/collateral release dependency"
    ],
    "next_best_actions": [
      "Expedite pending closure processing",
      "Escalate to credit operations team for TAT breach",
      "Update LMS records post-closure",
      "Issue closure confirmation to relevant records"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Closure Request Pending",
    "investigation_steps": [
      "Check LMS closure request workflow stage and queue assignment",
      "Verify documentation/payment confirmation status required for closure",
      "Review pending approval log for the closure request"
    ],
    "next_best_actions": [
      "Expedite pending closure request processing",
      "Escalate to operations team for workflow delay",
      "Process closure upon verification completion",
      "Update LMS records post-closure"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Closed Loan Still Active",
    "investigation_steps": [
      "Check LMS account status flag against closure date and final settlement record",
      "Verify batch job/sync process responsible for status propagation",
      "Cross-check CBS and credit bureau reporting feed for status mismatch"
    ],
    "next_best_actions": [
      "Manually correct account status to closed across all systems",
      "Escalate to IT team for batch/sync job failure",
      "Update credit bureau reporting feed with correct status",
      "Verify status reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Closure Certificate Not Issued",
    "investigation_steps": [
      "Check LMS/document generation log for closure certificate request status",
      "Verify closure confirmation status as prerequisite for certificate generation",
      "Review document dispatch/delivery log"
    ],
    "next_best_actions": [
      "Generate and issue closure certificate",
      "Escalate to documentation team for generation failure",
      "Confirm receipt and update LMS records",
      "Provide duplicate copy if required"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "NOC Delay",
    "investigation_steps": [
      "Check LMS NOC request workflow stage and pending approval log",
      "Verify closure/settlement confirmation status as prerequisite for NOC issuance",
      "Review document generation/dispatch TAT compliance"
    ],
    "next_best_actions": [
      "Expedite pending NOC processing and issuance",
      "Escalate to operations team for TAT breach",
      "Generate and dispatch NOC immediately upon eligibility confirmation",
      "Update LMS records post-issuance"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "NOC Not Issued",
    "investigation_steps": [
      "Check LMS NOC request log and generation status",
      "Verify closure/settlement confirmation status as prerequisite",
      "Review document generation service error log if applicable"
    ],
    "next_best_actions": [
      "Generate and issue NOC",
      "Escalate to documentation/IT team for generation failure",
      "Confirm receipt and update LMS records",
      "Provide duplicate copy if required"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "No Dues Certificate Not Issued",
    "investigation_steps": [
      "Check LMS no-dues certificate request log and generation status",
      "Verify outstanding balance is nil as prerequisite for certificate issuance",
      "Review document generation service error log if applicable"
    ],
    "next_best_actions": [
      "Generate and issue no-dues certificate",
      "Escalate to documentation/IT team for generation failure",
      "Confirm receipt and update LMS records",
      "Provide duplicate copy if required"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Closure Confirmation Not Received",
    "investigation_steps": [
      "Check LMS closure confirmation generation and dispatch log",
      "Verify email/SMS/document delivery log for the confirmation",
      "Review document generation service error log if applicable"
    ],
    "next_best_actions": [
      "Regenerate and resend closure confirmation",
      "Escalate to documentation/IT team for dispatch failure",
      "Confirm receipt and update LMS records",
      "Provide duplicate copy if required"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Lien Not Removed",
    "investigation_steps": [
      "Check CBS/LMS lien marking log against loan closure status",
      "Verify lien removal request workflow status",
      "Review dependency (final settlement/charge clearance) blocking removal"
    ],
    "next_best_actions": [
      "Process pending lien removal request",
      "Escalate to operations team for workflow delay",
      "Update CBS/LMS records to reflect lien removal",
      "Verify account reflects lien-free status post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Collateral Not Released",
    "investigation_steps": [
      "Check collateral management system log for release request status",
      "Verify loan closure/settlement confirmation as prerequisite for release",
      "Review custody/vault log for the collateral item"
    ],
    "next_best_actions": [
      "Process pending collateral release",
      "Escalate to operations/custody team for workflow delay",
      "Update collateral management records post-release",
      "Confirm release and obtain customer acknowledgment"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Property Documents Not Returned",
    "investigation_steps": [
      "Check document custody/vault log for the property document set",
      "Verify loan closure confirmation as prerequisite for document return",
      "Review document return request workflow status"
    ],
    "next_best_actions": [
      "Process pending property document return",
      "Escalate to operations/custody team for workflow delay",
      "Update document custody records post-return",
      "Confirm return and obtain customer acknowledgment"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Vehicle Hypothecation Not Removed",
    "investigation_steps": [
      "Check RC/hypothecation removal request log with RTO authority",
      "Verify loan closure confirmation as prerequisite for hypothecation removal",
      "Review NOC/Form 35 generation and dispatch status"
    ],
    "next_best_actions": [
      "Generate and submit hypothecation removal documentation (NOC/Form 35) to RTO",
      "Escalate to operations team for processing delay",
      "Update LMS records post-removal confirmation",
      "Provide duplicate NOC if required by customer"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Gold Collateral Not Returned",
    "investigation_steps": [
      "Check gold collateral custody/vault log for the pledged item",
      "Verify loan closure/settlement confirmation as prerequisite for release",
      "Review release request workflow and appraisal verification log"
    ],
    "next_best_actions": [
      "Process pending gold collateral release after verification",
      "Escalate to operations/custody team for workflow delay",
      "Update vault/custody records post-release",
      "Confirm release and obtain customer acknowledgment"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Security Deposit Not Refunded",
    "investigation_steps": [
      "Check LMS/CBS log for security deposit refund request status",
      "Verify loan closure confirmation and adjustment against outstanding dues",
      "Review refund processing workflow and payment log"
    ],
    "next_best_actions": [
      "Process pending security deposit refund",
      "Escalate to operations team for workflow delay",
      "Update LMS/CBS records post-refund",
      "Confirm refund credit to customer account"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Guarantee Release Pending",
    "investigation_steps": [
      "Check LMS guarantee release request workflow status",
      "Verify loan closure/settlement confirmation as prerequisite for release",
      "Review guarantor record update log"
    ],
    "next_best_actions": [
      "Process pending guarantee release",
      "Escalate to operations team for workflow delay",
      "Update LMS records and guarantor status post-release",
      "Issue release confirmation to guarantor"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Mortgage Release Pending",
    "investigation_steps": [
      "Check LMS/registrar mortgage release request workflow status",
      "Verify loan closure confirmation as prerequisite for release",
      "Review documentation (release deed) generation and submission status"
    ],
    "next_best_actions": [
      "Generate and submit mortgage release documentation to registrar/authority",
      "Escalate to legal/operations team for processing delay",
      "Update LMS records post-release confirmation",
      "Provide duplicate release deed if required"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Title Deed Not Returned",
    "investigation_steps": [
      "Check document custody/vault log for the title deed",
      "Verify loan closure confirmation as prerequisite for document return",
      "Review document return request workflow status"
    ],
    "next_best_actions": [
      "Process pending title deed return",
      "Escalate to operations/custody team for workflow delay",
      "Update document custody records post-return",
      "Confirm return and obtain customer acknowledgment"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Collateral Valuation Dispute",
    "investigation_steps": [
      "Check collateral valuation report and methodology used by empaneled valuer",
      "Verify valuation date and market reference data applied",
      "Review policy guidelines for valuation dispute resolution"
    ],
    "next_best_actions": [
      "Arrange re-valuation through an independent empaneled valuer if discrepancy confirmed",
      "Escalate to credit risk team for valuation policy review",
      "Update collateral records with revised valuation if applicable",
      "Communicate resolution outcome internally"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Account Freeze",
    "investigation_steps": [
      "Check LMS/CBS account status flag for freeze trigger reason and timestamp",
      "Verify fraud/risk/compliance system log for the freeze trigger event",
      "Review any court order/regulatory directive linked to the freeze"
    ],
    "next_best_actions": [
      "Unfreeze account if freeze found unwarranted post-verification",
      "Escalate to risk/compliance team if freeze is regulatory/court-mandated and requires further action",
      "Update LMS/CBS records post-resolution",
      "Communicate freeze status resolution internally"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Account Blocked",
    "investigation_steps": [
      "Check LMS/CBS account status flag for block reason and trigger event",
      "Verify risk/compliance system log for the block trigger",
      "Review block request history (customer-initiated/system-triggered)"
    ],
    "next_best_actions": [
      "Unblock account post identity/eligibility verification if block found unwarranted",
      "Escalate to risk/compliance team for further review if required",
      "Update LMS/CBS access status records",
      "Verify account access restored post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Account Access Denied",
    "investigation_steps": [
      "Check channel/portal access log for the denial reason code",
      "Verify LMS/CBS account status and customer authentication mapping",
      "Review access control configuration for the loan account"
    ],
    "next_best_actions": [
      "Restore access if denial found erroneous",
      "Escalate to IT/access management team for configuration fix",
      "Update access control records",
      "Verify access restored with test login"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Account Mapping Incorrect",
    "investigation_steps": [
      "Check LMS/CBS customer-to-account mapping configuration",
      "Verify data entry log at loan account setup/migration stage",
      "Cross-check linked customer ID against actual loan applicant record"
    ],
    "next_best_actions": [
      "Correct account mapping in LMS/CBS",
      "Escalate to data/IT team for migration or entry error root cause",
      "Update all downstream system records post-correction",
      "Verify mapping reflects correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Account Missing",
    "investigation_steps": [
      "Check LMS/CBS database for the loan account record using application/loan reference number",
      "Verify data migration/sync log if account expected post system migration",
      "Review account creation log at disbursement stage"
    ],
    "next_best_actions": [
      "Restore missing account record from backup/archival data",
      "Escalate to IT/data team for migration or sync issue",
      "Recreate account record with accurate data if restoration not possible",
      "Verify account appears correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Details Not Visible",
    "investigation_steps": [
      "Check channel/portal API log for loan details retrieval request",
      "Verify LMS/CBS data sync status with the customer-facing display module",
      "Review account-to-customer ID mapping for the linked profile"
    ],
    "next_best_actions": [
      "Escalate to IT/middleware team for API/sync failure",
      "Correct account mapping if found incorrect",
      "Trigger manual data refresh/sync",
      "Verify loan details display correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Balance Not Updated",
    "investigation_steps": [
      "Check LMS posting log for the latest transaction against displayed balance",
      "Verify batch/real-time balance update job status",
      "Cross-check CBS/LMS sync for the balance field"
    ],
    "next_best_actions": [
      "Trigger manual balance sync/update",
      "Escalate to LMS/batch processing team if job failure confirmed",
      "Reconcile loan account records",
      "Verify balance displays correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan History Missing",
    "investigation_steps": [
      "Check LMS transaction log retrieval query for the loan account",
      "Verify data archival/retention status for historical entries",
      "Cross-check data migration log if history expected post system migration"
    ],
    "next_best_actions": [
      "Restore missing history entries from archival/backup data",
      "Escalate to IT/data team for migration or query logic fix",
      "Update loan account history records",
      "Verify resolution by re-querying transaction history"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Duplicate Loan Account",
    "investigation_steps": [
      "Check LMS/CBS for multiple account records against single sanctioned loan",
      "Verify disbursement and account creation log for duplicate entry trigger",
      "Cross-check customer ID/application reference mapping for both records"
    ],
    "next_best_actions": [
      "Merge/deactivate the duplicate account record",
      "Reconcile transactions between duplicate accounts into the correct account",
      "Escalate to IT/data team for account creation logic error",
      "Update credit bureau reporting feed post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Incorrect Loan Type",
    "investigation_steps": [
      "Check LMS account configuration against sanctioned loan product type",
      "Verify product code mapping at account setup/disbursement stage",
      "Review sanction letter/loan agreement for the approved product type"
    ],
    "next_best_actions": [
      "Correct loan product/type configuration in LMS",
      "Recalculate interest/charges if product-specific terms differ",
      "Escalate to operations team for setup error root cause",
      "Update loan account records post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Credit Bureau Not Updated",
    "investigation_steps": [
      "Check credit bureau reporting feed/batch job log for the account",
      "Verify data extract completeness for the reporting cycle",
      "Review bureau acknowledgment/rejection file for the submission"
    ],
    "next_best_actions": [
      "Resubmit corrected data in the next reporting cycle",
      "Escalate to credit bureau reporting team for batch job failure",
      "Verify bureau reflects updated status post-resubmission",
      "Reconcile reporting acknowledgment file"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "CIBIL Not Updated After Loan Closure",
    "investigation_steps": [
      "Check credit bureau reporting feed for the closure status update against the account",
      "Verify closure date and reporting cycle alignment",
      "Review bureau acknowledgment/rejection file for the submission"
    ],
    "next_best_actions": [
      "Resubmit corrected closure status in the next reporting cycle",
      "Escalate to credit bureau reporting team for batch job failure",
      "Verify CIBIL reflects closed status post-resubmission",
      "Reconcile reporting acknowledgment file"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Showing Active in Credit Report",
    "investigation_steps": [
      "Check LMS account status against credit bureau reporting feed for the account",
      "Verify reporting cycle and data extract used for the bureau submission",
      "Review bureau acknowledgment file for status mismatch"
    ],
    "next_best_actions": [
      "Resubmit corrected status (closed) in the next reporting cycle",
      "Escalate to credit bureau reporting team for sync/batch job failure",
      "Verify credit report reflects correct status post-resubmission",
      "Reconcile reporting acknowledgment file"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Wrong Loan Status in Credit Report",
    "investigation_steps": [
      "Check LMS account status against credit bureau reporting feed for discrepancy",
      "Verify reporting data extract logic and mapping for status field",
      "Review bureau acknowledgment file for the submission"
    ],
    "next_best_actions": [
      "Resubmit corrected status in the next reporting cycle",
      "Escalate to credit bureau reporting team for mapping/extract error",
      "Verify credit report reflects correct status post-resubmission",
      "Reconcile reporting acknowledgment file"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Incorrect Outstanding in Credit Report",
    "investigation_steps": [
      "Check LMS outstanding balance against credit bureau reporting feed data",
      "Verify reporting data extract logic for the outstanding balance field",
      "Review bureau acknowledgment file for the submission"
    ],
    "next_best_actions": [
      "Resubmit corrected outstanding balance in the next reporting cycle",
      "Escalate to credit bureau reporting team for extract/calculation error",
      "Verify credit report reflects correct outstanding post-resubmission",
      "Reconcile reporting acknowledgment file"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Duplicate Loan in Credit Report",
    "investigation_steps": [
      "Check credit bureau reporting feed for multiple submissions against the same loan account",
      "Verify LMS account record for any duplicate account creation",
      "Review reporting batch job log for repeated submission"
    ],
    "next_best_actions": [
      "Submit correction/deletion request to credit bureau for the duplicate entry",
      "Resolve underlying duplicate account in LMS if applicable",
      "Escalate to credit bureau reporting team for batch job error",
      "Verify credit report reflects single accurate entry post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Default Reported Incorrectly",
    "investigation_steps": [
      "Check LMS payment/DPD (days past due) log against the reported default status",
      "Verify reporting data extract logic for default classification",
      "Review payment history for any unposted/misapplied payment causing incorrect classification"
    ],
    "next_best_actions": [
      "Submit correction request to credit bureau removing incorrect default classification",
      "Correct underlying payment posting in LMS if misapplied payment identified",
      "Escalate to credit bureau reporting team for classification logic error",
      "Verify credit report reflects corrected status post-resubmission"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Late Payment Reported Incorrectly",
    "investigation_steps": [
      "Check LMS payment date log against the due date and reported DPD status",
      "Verify NACH/auto-debit execution date versus due date for processing delay",
      "Review reporting data extract logic for DPD calculation"
    ],
    "next_best_actions": [
      "Submit correction request to credit bureau if late payment reporting found erroneous",
      "Correct underlying payment date/DPD calculation in LMS if processing delay caused misclassification",
      "Escalate to credit bureau reporting team for extract error",
      "Verify credit report reflects corrected status post-resubmission"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Written Off Incorrectly",
    "investigation_steps": [
      "Check LMS write-off approval log and trigger event for the account",
      "Verify outstanding balance and payment history at the time of write-off classification",
      "Review reporting data extract logic for write-off status"
    ],
    "next_best_actions": [
      "Submit correction request to credit bureau if write-off found erroneous",
      "Reverse incorrect write-off classification in LMS if account was current/settled",
      "Escalate to credit operations team for classification error root cause",
      "Verify credit report reflects corrected status post-resubmission"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Credit Score Affected Due to Bank Error",
    "investigation_steps": [
      "Check LMS/reporting log for the specific erroneous entry impacting the credit score (status/DPD/outstanding)",
      "Verify root cause of the bank-side data error",
      "Review credit bureau acknowledgment/correction submission history"
    ],
    "next_best_actions": [
      "Submit correction request to credit bureau for the erroneous entry",
      "Correct underlying data error in LMS",
      "Escalate to credit bureau reporting team for resubmission",
      "Verify credit report reflects corrected data post-resubmission"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Insurance Charged Without Consent",
    "investigation_steps": [
      "Check LOS/LMS consent capture log for the insurance product at loan origination",
      "Verify insurance premium debit entry against documented customer consent",
      "Review loan agreement/sanction letter for insurance bundling terms"
    ],
    "next_best_actions": [
      "Refund premium if consent not validly obtained",
      "Escalate to compliance/credit policy team for consent process review",
      "Cancel insurance policy if applicable and process refund",
      "Update LMS records post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Insurance Claim Not Processed",
    "investigation_steps": [
      "Check insurer claim submission log and processing status",
      "Verify claim document completeness submitted to insurer",
      "Review insurer response/settlement status for the claim"
    ],
    "next_best_actions": [
      "Follow up with insurer for pending claim processing",
      "Escalate to insurance operations team for documentation gap",
      "Resubmit claim with complete documentation if required",
      "Update LMS records upon claim settlement"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Insurance Premium Incorrect",
    "investigation_steps": [
      "Check LMS insurance premium calculation against policy terms and sum assured",
      "Verify premium debit entry against insurer-confirmed premium amount",
      "Review any data entry error at policy issuance stage"
    ],
    "next_best_actions": [
      "Correct premium amount and refund excess if overcharged",
      "Escalate to insurance operations team for calculation error",
      "Update LMS records post-correction",
      "Coordinate with insurer for policy/premium record correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Subsidy Not Applied",
    "investigation_steps": [
      "Check LMS subsidy eligibility and application log for the scheme (e.g., PMAY/interest subsidy)",
      "Verify subsidy claim submission status to the nodal agency",
      "Review documentation completeness required for subsidy application"
    ],
    "next_best_actions": [
      "Submit/resubmit subsidy application with complete documentation",
      "Escalate to subsidy processing team for pending application",
      "Apply subsidy credit to loan account upon approval",
      "Update LMS records post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Interest Subsidy Not Credited",
    "investigation_steps": [
      "Check nodal agency/government portal log for subsidy disbursement status",
      "Verify LMS posting log for subsidy credit against approved claim",
      "Review subsidy claim approval and amount confirmation"
    ],
    "next_best_actions": [
      "Follow up with nodal agency for pending subsidy disbursement",
      "Post subsidy credit to loan account upon receipt confirmation",
      "Escalate to subsidy processing team for unresolved delay",
      "Update LMS records post-credit"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Government Subsidy Pending",
    "investigation_steps": [
      "Check subsidy application/claim status in the nodal agency portal",
      "Verify documentation submission completeness for the subsidy scheme",
      "Review LMS records for claim submission and tracking reference"
    ],
    "next_best_actions": [
      "Follow up with nodal agency for pending subsidy approval/disbursement",
      "Resubmit documentation if found incomplete",
      "Escalate to subsidy processing team for unresolved delay",
      "Update LMS records upon resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Restructuring Request Pending",
    "investigation_steps": [
      "Check LMS restructuring request workflow stage and pending approval log",
      "Verify eligibility assessment status (income/repayment capacity) for restructuring",
      "Review credit committee/approval authority action log"
    ],
    "next_best_actions": [
      "Expedite pending restructuring approval",
      "Escalate to credit operations team for workflow delay",
      "Apply approved restructuring terms to the loan account",
      "Update LMS records post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Moratorium Not Applied",
    "investigation_steps": [
      "Check LMS moratorium request/approval log for the account",
      "Verify eligibility criteria applied for moratorium grant",
      "Review batch job/workflow status for applying the moratorium to the repayment schedule"
    ],
    "next_best_actions": [
      "Apply approved moratorium to the loan account and revise schedule",
      "Escalate to LMS/credit operations team for workflow delay",
      "Update LMS records post-application",
      "Communicate revised repayment schedule"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Settlement Amount Incorrect",
    "investigation_steps": [
      "Check LMS settlement amount calculation against outstanding balance and approved settlement terms",
      "Verify waiver/write-off component applied in the calculation",
      "Review approval authority sign-off for the settlement terms"
    ],
    "next_best_actions": [
      "Recalculate and correct settlement amount as per approved terms",
      "Escalate to credit operations team for calculation error",
      "Update LMS records post-correction",
      "Communicate corrected settlement amount"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Settlement Letter Not Issued",
    "investigation_steps": [
      "Check LMS/document generation log for settlement letter request status",
      "Verify settlement payment confirmation as prerequisite for letter issuance",
      "Review document dispatch/delivery log"
    ],
    "next_best_actions": [
      "Generate and issue settlement letter",
      "Escalate to documentation team for generation failure",
      "Confirm receipt and update LMS records",
      "Provide duplicate copy if required"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Recovery Agent Harassment",
    "investigation_steps": [
      "Review recovery agent call/visit log and communication record for the account",
      "Verify recovery agency compliance with RBI fair practices code and bank's collection policy",
      "Check complaint history and any prior advisory issued to the agency"
    ],
    "next_best_actions": [
      "Issue formal advisory/warning to the recovery agency",
      "Suspend agency's access to the account pending investigation",
      "Escalate to collections compliance team for policy violation review",
      "Communicate resolution and corrective action taken"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Collection Calls After Loan Closure",
    "investigation_steps": [
      "Check LMS account closure status and closure date against collection call log",
      "Verify collections system sync with LMS for account status",
      "Review recovery agency assignment list for the closed account"
    ],
    "next_best_actions": [
      "Remove closed account from active collection assignment immediately",
      "Escalate to IT team for collections system sync failure",
      "Issue advisory to recovery agency to cease contact",
      "Verify account removed from collection workflow post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Wrong Recovery Notice",
    "investigation_steps": [
      "Check LMS account status and outstanding balance against the recovery notice issued",
      "Verify notice generation log and data source used",
      "Review approval workflow for notice issuance"
    ],
    "next_best_actions": [
      "Withdraw/correct the erroneous recovery notice",
      "Issue corrected notice if account status warrants it",
      "Escalate to operations/legal team for data error root cause",
      "Update LMS records post-correction"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Legal Notice Issued Incorrectly",
    "investigation_steps": [
      "Check LMS account status and default classification against the legal notice trigger criteria",
      "Verify legal/collections workflow approval log for notice issuance",
      "Review data source used for notice generation"
    ],
    "next_best_actions": [
      "Withdraw the erroneous legal notice",
      "Escalate to legal/compliance team for review and corrective communication",
      "Correct underlying account status/classification error",
      "Update LMS records post-resolution"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Complaint Resolution Delay",
    "investigation_steps": [
      "Review complaint case history and all prior investigation actions taken",
      "Check status of related LMS/LOS/credit bureau investigation entries",
      "Verify reasons for delay or non-closure in the complaint tracking system"
    ],
    "next_best_actions": [
      "Reassign complaint for expedited resolution",
      "Complete pending investigation steps and close the case",
      "Update complaint tracking system with final resolution",
      "Escalate to next level if unresolved beyond defined cycle"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Branch Not Responding for Loan Query",
    "investigation_steps": [
      "Check branch service request/query log for response status",
      "Verify query escalation/tracking entry assigned to the branch",
      "Review branch service TAT compliance record"
    ],
    "next_best_actions": [
      "Escalate query to branch manager/regional operations for response",
      "Reassign query to alternate service channel if branch unresponsive",
      "Update tracking system with resolution status",
      "Review branch service process for recurring non-response issue"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Customer Support Not Responding",
    "investigation_steps": [
      "Check customer support ticket log for the query/complaint status",
      "Verify queue assignment and agent response SLA compliance",
      "Review escalation log for the unresponded ticket"
    ],
    "next_best_actions": [
      "Reassign ticket for immediate response",
      "Escalate to support operations team for SLA breach",
      "Update ticket tracking system with resolution status",
      "Review support process for recurring non-response issue"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Service Request Pending",
    "investigation_steps": [
      "Check LMS service request module log for the request workflow stage",
      "Verify pending approval/processing queue status",
      "Review dependency blocking request completion"
    ],
    "next_best_actions": [
      "Expedite pending service request processing",
      "Escalate to operations team for workflow delay",
      "Process request upon dependency resolution",
      "Update LMS records post-completion"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan Nominee Update Pending",
    "investigation_steps": [
      "Check LMS nominee update request log and workflow/approval status",
      "Verify nominee detail validation against submitted request",
      "Review maker-checker approval queue status"
    ],
    "next_best_actions": [
      "Expedite pending nominee update approval",
      "Escalate to operations team for workflow delay",
      "Update LMS records post-approval",
      "Verify nominee details updated correctly post-fix"
    ]
  },
  {
    "major_issue": "Loans",
    "sub_issue": "Loan KYC Pending",
    "investigation_steps": [
      "Check LMS/KYC verification workflow status and document validation queue",
      "Verify source verification (Aadhaar/PAN/CKYC) API response status",
      "Review maker-checker approval queue for pending KYC verification"
    ],
    "next_best_actions": [
      "Expedite pending KYC verification processing",
      "Escalate to KYC/compliance operations team for backlog",
      "Update LMS KYC status post-verification",
      "Verify loan account service access restored if KYC was blocking"
    ]
  }
],
[
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Opening Delay",
    "investigation_steps": [
      "Review account opening application status in CBS",
      "Check CIF (Customer Information File) creation timestamp",
      "Verify document upload completeness in onboarding portal",
      "Check KYC verification queue status",
      "Review pending approvals or maker-checker workflow stage",
      "Verify branch processing logs for application receipt date"
    ],
    "next_best_actions": [
      "Escalate pending application to branch operations supervisor",
      "Trigger KYC verification if documents are complete",
      "Complete CIF creation and account number generation in CBS",
      "Update application status in onboarding system",
      "Notify branch to expedite processing within SLA"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Opening Rejected",
    "investigation_steps": [
      "Retrieve rejection reason code from CBS or onboarding system",
      "Review KYC document verification outcome",
      "Check deduplication results for existing CIF",
      "Verify CKYC registry response for customer",
      "Review blacklist/negative list screening results",
      "Check if rejection was system-generated or manual"
    ],
    "next_best_actions": [
      "Document rejection reason in system with proper reason code",
      "Initiate re-verification if rejection was due to document quality",
      "Correct data entry errors and resubmit if applicable",
      "Escalate to compliance team if blacklist flag is erroneous",
      "Update CIF and reprocess application if CKYC data mismatch is resolved"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Not Activated",
    "investigation_steps": [
      "Check account status in CBS (Inactive/Dormant/Pending)",
      "Verify if initial funding/first deposit has been received",
      "Review onboarding checklist completion status",
      "Check for pending KYC or document verification flags",
      "Verify video KYC or biometric verification status if applicable"
    ],
    "next_best_actions": [
      "Activate account in CBS upon confirming KYC and funding requirements are met",
      "Clear pending verification flags in onboarding system",
      "Update account status from Inactive to Active in CBS",
      "Trigger welcome kit dispatch post activation"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Activation Pending",
    "investigation_steps": [
      "Verify activation workflow stage in CBS or middleware",
      "Check for pending maker-checker approvals",
      "Review KYC document status in verification queue",
      "Check for system errors or exceptions in activation process log",
      "Verify if branch officer sign-off is pending"
    ],
    "next_best_actions": [
      "Complete pending maker-checker approval in CBS",
      "Resubmit activation request if workflow exception is identified",
      "Coordinate with branch to obtain pending sign-off",
      "Manually activate account after verifying all prerequisites are met"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Number Not Generated",
    "investigation_steps": [
      "Check CBS for CIF creation status",
      "Verify if account number generation failed due to product code error",
      "Review error logs in CBS for account creation module",
      "Check IFSC and branch code mapping in CBS",
      "Verify if system batch job for account number generation is pending"
    ],
    "next_best_actions": [
      "Manually trigger account number generation in CBS",
      "Correct product/branch code mapping if found erroneous",
      "Retry account creation process in CBS",
      "Coordinate with IT/CBS team to resolve batch job failure"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Welcome Kit Not Received",
    "investigation_steps": [
      "Verify dispatch status in welcome kit management system",
      "Check courier tracking details and delivery confirmation",
      "Verify registered address captured in CBS",
      "Check if welcome kit was returned undelivered"
    ],
    "next_best_actions": [
      "Initiate re-dispatch of welcome kit to verified address",
      "Update address in CBS if incorrect address caused non-delivery",
      "Coordinate with courier partner to trace undelivered kit",
      "Log re-dispatch request in service request management system"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Passbook Not Issued",
    "investigation_steps": [
      "Check passbook issuance request status in CBS or branch system",
      "Verify if passbook printing was triggered at account opening",
      "Review branch passbook inventory and dispatch records",
      "Check if account type is eligible for physical passbook"
    ],
    "next_best_actions": [
      "Raise passbook issuance request in CBS",
      "Coordinate with branch to print and dispatch passbook",
      "Update passbook issuance status in customer record"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Cheque Book Not Received",
    "investigation_steps": [
      "Verify cheque book request status in CBS",
      "Check CTS-compliant cheque book dispatch status",
      "Verify courier tracking and delivery confirmation",
      "Check if cheque book was returned undelivered",
      "Verify registered address in CBS"
    ],
    "next_best_actions": [
      "Initiate re-dispatch of cheque book if not delivered",
      "Update address in CBS if address mismatch identified",
      "Coordinate with courier partner to trace undelivered item",
      "Raise new cheque book request in CBS if original not dispatched"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Debit Card Not Received",
    "investigation_steps": [
      "Verify debit card issuance and dispatch status in card management system",
      "Check courier/speed post tracking details",
      "Verify registered address in CBS matches card dispatch address",
      "Check if card was returned undelivered to bank",
      "Verify card status in card management system (Issued/In Transit/Returned)"
    ],
    "next_best_actions": [
      "Initiate re-dispatch of debit card to verified address",
      "Hot-list returned card and issue a replacement card",
      "Update address in CBS if mismatch identified",
      "Update card management system with re-dispatch details"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Welcome Letter Not Received",
    "investigation_steps": [
      "Verify welcome letter generation and dispatch status in system",
      "Check if letter was dispatched via courier or postal mail",
      "Verify registered address in CBS",
      "Check for returned mail records"
    ],
    "next_best_actions": [
      "Initiate re-dispatch of welcome letter",
      "Update address in CBS if incorrect",
      "Provide digital copy of welcome letter if physical delivery is not feasible"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Freeze Without Notice",
    "investigation_steps": [
      "Check CBS for freeze reason code and triggering authority",
      "Review court order, regulatory directive, or internal risk flag that caused freeze",
      "Verify if freeze was applied due to AML/fraud alert",
      "Check if customer was notified as per process",
      "Review communication logs for any freeze notification sent"
    ],
    "next_best_actions": [
      "Document freeze reason with proper authority reference in CBS",
      "Coordinate with legal/compliance team to confirm freeze validity",
      "Issue formal communication to customer if freeze is valid",
      "Initiate unfreeze process if freeze was applied erroneously"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Blocked",
    "investigation_steps": [
      "Retrieve account block reason code from CBS",
      "Check if block was triggered by fraud, regulatory, legal, or risk team",
      "Review fraud detection system alerts linked to the account",
      "Verify customer KYC status and pending documentation"
    ],
    "next_best_actions": [
      "Coordinate with risk/compliance/legal team to validate block",
      "Initiate account unblock in CBS if block was erroneous",
      "Obtain required documentation from customer if KYC-related block",
      "Update CBS with unblock remarks post resolution"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Debit Blocked",
    "investigation_steps": [
      "Check CBS for debit block flag and associated reason code",
      "Verify if debit block was applied due to court order, lien, or risk team instruction",
      "Review account transaction history for suspicious activity",
      "Check if minimum balance penalty or regulatory hold triggered debit block"
    ],
    "next_best_actions": [
      "Coordinate with authorizing team to validate debit block",
      "Remove debit block in CBS if applied erroneously",
      "Update CBS records with resolution remarks",
      "Notify relevant team if debit block is to be retained"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Credit Blocked",
    "investigation_steps": [
      "Check CBS for credit block flag and triggering reason",
      "Verify if credit block was applied by regulatory, legal, or fraud team",
      "Review FEMA/AML compliance flags on the account",
      "Check if credit block is linked to ongoing investigation"
    ],
    "next_best_actions": [
      "Validate credit block with compliance or legal team",
      "Remove credit block in CBS if applied in error",
      "Ensure all pending credits are processed post unblocking",
      "Update CBS with resolution action and authority"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Restricted",
    "investigation_steps": [
      "Check CBS for restriction type and reason code",
      "Review KYC re-verification or pending documentation flag",
      "Verify regulatory instruction or internal risk policy that triggered restriction",
      "Check communication logs for restriction notification to customer"
    ],
    "next_best_actions": [
      "Resolve the underlying reason for restriction (KYC, documentation, compliance)",
      "Remove restriction in CBS post resolution",
      "Update customer communication log with resolution details"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Locked",
    "investigation_steps": [
      "Check CBS for account lock reason (internet banking attempts, internal lock, regulatory)",
      "Verify if lock was triggered by multiple failed login attempts in internet banking",
      "Review security incident logs",
      "Check if lock was manually applied by branch or operations team"
    ],
    "next_best_actions": [
      "Unlock account in CBS or internet banking system after identity verification",
      "Reset internet banking credentials if lock is login-related",
      "Coordinate with branch to manually unlock if branch-initiated",
      "Update security event log with resolution details"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Dormant Account Activation Delay",
    "investigation_steps": [
      "Verify account dormancy status in CBS",
      "Check dormant account activation request submission and processing status",
      "Verify KYC re-verification completion status",
      "Review branch processing queue for dormant activation requests"
    ],
    "next_best_actions": [
      "Complete KYC re-verification if pending",
      "Process dormant account activation in CBS",
      "Update account status from Dormant to Active in CBS",
      "Ensure all restrictions imposed due to dormancy are lifted"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Inactive Account Not Reactivated",
    "investigation_steps": [
      "Check CBS for account status and inactivity period",
      "Verify if reactivation request was submitted",
      "Review pending KYC or documentation requirements for reactivation",
      "Check branch processing log for reactivation request"
    ],
    "next_best_actions": [
      "Process reactivation in CBS upon KYC completion",
      "Update account status from Inactive to Active",
      "Remove transaction restrictions imposed during inactivity"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Joint Account Not Updated",
    "investigation_steps": [
      "Verify joint account holder update request status in CBS",
      "Check submitted documentation for joint holder addition/modification",
      "Review maker-checker approval status in CBS for joint account changes",
      "Verify CKYC/KYC status of the new joint holder"
    ],
    "next_best_actions": [
      "Complete KYC of new joint holder and update CBS",
      "Process joint account modification after completing maker-checker approval",
      "Update account operating instructions (Either/Survivor, Jointly, etc.) in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Minor Account Conversion Pending",
    "investigation_steps": [
      "Verify minor account holder's age and date of birth in CBS",
      "Check if conversion request to regular savings account was submitted",
      "Review pending KYC documentation for the newly major customer",
      "Verify maker-checker workflow status for account conversion"
    ],
    "next_best_actions": [
      "Complete fresh KYC for the customer who has attained majority",
      "Convert minor account to regular savings account in CBS",
      "Update operating instructions and remove guardian mandate in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Cash Deposit Not Reflected",
    "investigation_steps": [
      "Verify deposit slip details against CBS transaction log",
      "Check vault/teller cash reconciliation records for the date of deposit",
      "Review branch teller system logs for the deposit transaction",
      "Check if deposit was processed under correct account number"
    ],
    "next_best_actions": [
      "Credit the account in CBS after confirming vault reconciliation",
      "Correct posting to right account if credited to wrong account",
      "Initiate inter-branch reconciliation if deposit was made at another branch"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Cash Deposit Pending",
    "investigation_steps": [
      "Check CBS transaction status for the deposit",
      "Verify teller EOD (End of Day) processing status",
      "Review branch batch processing logs",
      "Check if deposit is in a suspense or pending queue"
    ],
    "next_best_actions": [
      "Process pending deposit from suspense queue to customer account",
      "Coordinate with branch to complete EOD batch posting",
      "Update CBS with completed deposit transaction"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Cash Deposit Failed",
    "investigation_steps": [
      "Review CBS and teller system error logs for deposit failure",
      "Check if failure was due to account restrictions or system downtime",
      "Verify if cash was collected but not posted",
      "Review CDM (Cash Deposit Machine) logs if applicable"
    ],
    "next_best_actions": [
      "Post deposit manually in CBS after verification",
      "Ensure account restrictions are resolved before retrying",
      "Reconcile CDM cash with CBS records and credit customer account"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Cash Withdrawal Failed",
    "investigation_steps": [
      "Check CBS for withdrawal request status and failure reason code",
      "Verify available balance at time of withdrawal request",
      "Review teller system logs for failure event",
      "Check if account had debit block or lien at time of request"
    ],
    "next_best_actions": [
      "Process withdrawal in CBS if failure was due to system error",
      "Remove debit block if erroneously applied, then reprocess",
      "Advise branch teller team to reprocess transaction"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Cash Withdrawal Pending",
    "investigation_steps": [
      "Check CBS transaction queue for pending withdrawal",
      "Verify teller EOD batch processing completion",
      "Review if withdrawal is held in suspense account"
    ],
    "next_best_actions": [
      "Process pending withdrawal from suspense to customer account debit",
      "Complete EOD batch processing at branch",
      "Update CBS transaction status"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Wrong Balance Displayed",
    "investigation_steps": [
      "Compare CBS ledger balance with internet/mobile banking balance",
      "Check for pending transactions or holds affecting displayed balance",
      "Verify if lien amount is incorrectly deducted from displayed balance",
      "Review middleware/API response logs for balance fetch"
    ],
    "next_best_actions": [
      "Trigger balance refresh in internet/mobile banking system",
      "Correct lien or hold amount in CBS if incorrectly applied",
      "Reconcile middleware balance with CBS ledger balance",
      "Escalate to IT team if discrepancy is systemic"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Available Balance Incorrect",
    "investigation_steps": [
      "Check CBS for lien, hold, or earmark amounts on the account",
      "Verify clearing hold on recently deposited cheques",
      "Review any system-generated holds (minimum balance, charges)",
      "Compare ledger balance and available balance components in CBS"
    ],
    "next_best_actions": [
      "Remove erroneous lien or hold in CBS",
      "Release clearing hold if cheque has been cleared",
      "Correct available balance calculation parameters in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Ledger Balance Incorrect",
    "investigation_steps": [
      "Review CBS ledger for all debit and credit postings",
      "Verify reconciliation records for the affected period",
      "Check for duplicate postings or missing credits in CBS",
      "Review RTGS/NEFT/IMPS credit posting logs"
    ],
    "next_best_actions": [
      "Post missing credits in CBS after reconciliation confirmation",
      "Reverse duplicate debits in CBS",
      "Escalate to reconciliation team for adjustment entries"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Duplicate Debit",
    "investigation_steps": [
      "Retrieve all debit entries for the complained transaction in CBS",
      "Verify switch logs and payment gateway logs for duplicate processing",
      "Check settlement records for double debit confirmation",
      "Review NPCI/NACH records if ECS/NACH-related duplicate"
    ],
    "next_best_actions": [
      "Initiate reversal of duplicate debit entry in CBS",
      "Reconcile with NPCI/payment gateway to confirm duplicate settlement",
      "Credit customer account for the duplicate amount",
      "Log duplicate debit incident for fraud/ops review"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Unauthorized Debit",
    "investigation_steps": [
      "Retrieve debit transaction details from CBS",
      "Check switch/POS/ATM/digital channel logs for transaction initiation",
      "Verify if debit was initiated via ECS, NACH, or standing instruction",
      "Review fraud detection system alerts for the account",
      "Check for card or internet banking compromise"
    ],
    "next_best_actions": [
      "Initiate transaction dispute and chargeback process if applicable",
      "Block card or internet banking access if compromise suspected",
      "Raise fraud alert and block account credits/debits if required",
      "Coordinate with NPCI for chargeback if NACH/ECS-related",
      "Process provisional credit as per regulatory guidelines"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Unauthorized Credit",
    "investigation_steps": [
      "Identify credit transaction source in CBS",
      "Check if credit originated from NEFT/RTGS/IMPS with incorrect beneficiary posting",
      "Verify if credit was a system error or erroneous bulk credit",
      "Check with remitting bank for credit confirmation"
    ],
    "next_best_actions": [
      "Place lien on unauthorized credit amount pending investigation",
      "Initiate reversal to originating account",
      "Coordinate with remitting bank or NPCI for correction",
      "Report to compliance if suspicious credit origin"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Duplicate Credit",
    "investigation_steps": [
      "Retrieve all credit entries for the transaction in CBS",
      "Verify NEFT/RTGS/IMPS settlement records for duplicate posting",
      "Check NPCI logs for duplicate credit processing",
      "Review reconciliation records for the settlement date"
    ],
    "next_best_actions": [
      "Place lien on duplicate credit amount",
      "Reverse duplicate credit entry in CBS",
      "Reconcile with NPCI/settlement records",
      "Notify remitting bank if applicable"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Salary Credit Not Received",
    "investigation_steps": [
      "Verify employer's salary upload file processing status in CBS",
      "Check NACH or direct credit batch status for payroll date",
      "Verify if account number in employer's payroll records matches CBS",
      "Check if salary was credited to wrong account",
      "Review NPCI NACH return records"
    ],
    "next_best_actions": [
      "Process salary credit manually if batch file was processed but posting failed",
      "Coordinate with employer's bank for re-credit if returned",
      "Correct account number mapping if mismatch found",
      "Reconcile payroll batch settlement records"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Salary Credit Delayed",
    "investigation_steps": [
      "Check NACH batch processing timestamp for payroll date",
      "Verify cut-off time compliance for salary upload by employer",
      "Check NPCI settlement cycle for the payroll batch",
      "Review CBS posting queue for pending salary credit"
    ],
    "next_best_actions": [
      "Post salary credit from pending queue in CBS",
      "Coordinate with NPCI for expedited settlement if batch is delayed",
      "Notify employer's bank of delay for corrective action"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Government Benefit Not Credited",
    "investigation_steps": [
      "Verify DBT (Direct Benefit Transfer) payment status on PFMS/NPCI portal",
      "Check if account is linked to Aadhaar for DBT",
      "Verify NPCI mapper for correct account-Aadhaar linkage",
      "Check NACH/DBT batch credit records for the scheme",
      "Review return transaction records for rejected DBT"
    ],
    "next_best_actions": [
      "Update NPCI mapper with correct account-Aadhaar linkage",
      "Coordinate with government agency/PFMS for re-credit",
      "Process DBT credit manually if settlement file confirms payment",
      "Escalate to NPCI for mapper correction if linkage is incorrect"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Pension Not Credited",
    "investigation_steps": [
      "Check CBS for pension credit on scheduled pension date",
      "Verify CPPC (Central Pension Processing Centre) payment advice",
      "Check PFMS or pension disbursement authority's payment file",
      "Verify account is active and not blocked for credits"
    ],
    "next_best_actions": [
      "Coordinate with CPPC or pension disbursing authority for payment confirmation",
      "Process manual credit in CBS if payment advice confirms disbursement",
      "Ensure account restrictions are removed for pension credit"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Interest Not Credited",
    "investigation_steps": [
      "Check CBS interest accrual and credit schedule for the account",
      "Verify interest calculation batch run completion",
      "Check if account was in dormant/blocked status on interest credit date",
      "Verify applicable interest rate in CBS for the account type"
    ],
    "next_best_actions": [
      "Manually trigger interest posting in CBS if batch failed",
      "Correct interest rate if incorrectly applied",
      "Process backdated interest credit with appropriate GL entries"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Interest Calculated Incorrectly",
    "investigation_steps": [
      "Retrieve interest calculation details from CBS for the period",
      "Verify applicable savings account interest rate in CBS product parameters",
      "Check daily product balance used for interest calculation",
      "Verify if rate revision was correctly updated in CBS"
    ],
    "next_best_actions": [
      "Correct interest rate parameter in CBS",
      "Recalculate interest for the affected period",
      "Post differential interest credit or debit adjustment in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "TDS Deducted Incorrectly",
    "investigation_steps": [
      "Retrieve TDS deduction details from CBS for the financial year",
      "Verify PAN linkage and Form 15G/15H submission status",
      "Check TDS threshold and applicable rate in CBS",
      "Verify interest income against TDS calculation"
    ],
    "next_best_actions": [
      "Reverse excess TDS in CBS and update TDS records",
      "Update Form 15G/15H status in CBS if not recorded",
      "Coordinate with tax team for TDS correction and Form 26AS update",
      "Issue revised TDS certificate"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Minimum Balance Penalty Incorrect",
    "investigation_steps": [
      "Retrieve minimum balance charge details and applicable product parameters from CBS",
      "Verify average monthly balance (AMB) calculation for the period",
      "Check applicable minimum balance requirement for the account type/variant",
      "Review RBI and internal guidelines for minimum balance charge applicability"
    ],
    "next_best_actions": [
      "Reverse incorrect minimum balance charge in CBS",
      "Correct product parameter for minimum balance in CBS",
      "Recalculate AMB for the period and apply correct charge"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Wrong Charges Deducted",
    "investigation_steps": [
      "Retrieve charge deduction details and charge code from CBS",
      "Verify applicable fee schedule for the account type",
      "Check if charge was applied per product terms or erroneously",
      "Review fee revision circulars against charge applied date"
    ],
    "next_best_actions": [
      "Reverse incorrect charge in CBS",
      "Correct charge parameters in CBS product configuration",
      "Notify branch/operations of incorrect charge schedule in use"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Service Charges Incorrect",
    "investigation_steps": [
      "Retrieve service charge transaction details from CBS",
      "Verify applicable service charge schedule for account type and variant",
      "Compare applied charge with approved fee schedule",
      "Check if customer is enrolled in a fee waiver plan"
    ],
    "next_best_actions": [
      "Reverse incorrect service charge in CBS",
      "Apply correct charge as per approved fee schedule",
      "Update customer account for fee waiver plan if applicable"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Annual Maintenance Charges Incorrect",
    "investigation_steps": [
      "Retrieve AMC deduction details from CBS",
      "Verify applicable AMC for the account/card type",
      "Check if waiver criteria (balance, spends) were met",
      "Review card management system for AMC deduction record"
    ],
    "next_best_actions": [
      "Reverse incorrect AMC from CBS",
      "Apply correct AMC as per approved fee schedule",
      "Update waiver flag in CBS/card management system if waiver criteria are met"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "SMS Charges Incorrect",
    "investigation_steps": [
      "Retrieve SMS alert charge details from CBS",
      "Verify SMS alert subscription status for the account",
      "Check applicable SMS charge as per fee schedule",
      "Verify if customer opted out of SMS alerts"
    ],
    "next_best_actions": [
      "Reverse incorrect SMS charges in CBS",
      "Update SMS subscription status in CBS if opt-out was not recorded",
      "Apply correct charge per approved schedule"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Cheque Bounce Charges Incorrect",
    "investigation_steps": [
      "Retrieve cheque return charge details from CBS",
      "Verify applicable cheque return charge as per fee schedule",
      "Check CTS clearing system for cheque return reason code",
      "Verify if charge was applied for both inward and outward returns"
    ],
    "next_best_actions": [
      "Reverse incorrect cheque bounce charge in CBS",
      "Apply correct cheque return charge per approved schedule",
      "Update charge records in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "ECS Unauthorized Debit",
    "investigation_steps": [
      "Retrieve ECS debit transaction details from CBS",
      "Check NACH/ECS mandate records for the originating company",
      "Verify if customer had a valid mandate registered with the bank",
      "Review NPCI NACH records for mandate status",
      "Check if mandate was cancelled but debit was still processed"
    ],
    "next_best_actions": [
      "Initiate reversal of unauthorized ECS debit in CBS",
      "Coordinate with NPCI to cancel erroneous mandate",
      "Register mandate cancellation in CBS/NPCI NACH portal",
      "Escalate to NACH operations team for mandate dispute"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Standing Instruction Failed",
    "investigation_steps": [
      "Retrieve standing instruction details from CBS",
      "Verify available balance at time of standing instruction execution",
      "Check CBS processing logs for standing instruction failure reason",
      "Verify if beneficiary account details in standing instruction are correct"
    ],
    "next_best_actions": [
      "Retry standing instruction execution in CBS",
      "Correct beneficiary account details if incorrect",
      "Process manual fund transfer if standing instruction is time-sensitive",
      "Update standing instruction parameters in CBS if required"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Auto Debit Failed",
    "investigation_steps": [
      "Retrieve auto debit transaction details and failure reason from CBS",
      "Check available balance at auto debit execution time",
      "Verify if auto debit mandate is active in NPCI NACH system",
      "Review payment gateway or NACH system logs for failure details"
    ],
    "next_best_actions": [
      "Retry auto debit after ensuring sufficient balance",
      "Reactivate mandate in NPCI NACH system if deactivated",
      "Coordinate with biller/originator for re-presentation"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Recurring Payment Failed",
    "investigation_steps": [
      "Retrieve recurring payment transaction status from CBS and payment gateway",
      "Verify if recurring payment mandate/e-mandate is active",
      "Check available balance at recurring payment execution time",
      "Review RBI e-mandate processing logs"
    ],
    "next_best_actions": [
      "Retry recurring payment processing after balance verification",
      "Reactivate or re-register e-mandate if deactivated",
      "Coordinate with merchant/aggregator for re-initiation"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Mandate Registration Failed",
    "investigation_steps": [
      "Retrieve mandate registration request details from NPCI NACH portal",
      "Check failure reason code from NACH mandate registration response",
      "Verify account number and IFSC in mandate registration form",
      "Check if account type is eligible for NACH mandate",
      "Review NACH/NPCI rejection codes"
    ],
    "next_best_actions": [
      "Correct account number/IFSC and re-register mandate in NPCI NACH",
      "Coordinate with destination bank if rejection is from their end",
      "Resubmit mandate registration with correct details"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "NEFT Credit Not Received",
    "investigation_steps": [
      "Retrieve NEFT UTR number and check RBI NEFT settlement records",
      "Verify CBS for incoming NEFT credit posting",
      "Check if NEFT credit was posted to wrong account",
      "Review NEFT inward processing batch status",
      "Verify account status was active during settlement"
    ],
    "next_best_actions": [
      "Post NEFT credit in CBS if settlement confirmed but not posted",
      "Initiate return of funds to originating bank if account was blocked",
      "Correct posting to right account if credited to wrong account",
      "Coordinate with RBI NEFT settlement team if UTR is unresolved"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "RTGS Credit Not Received",
    "investigation_steps": [
      "Retrieve RTGS UTR number and check RBI RTGS settlement records",
      "Verify CBS for incoming RTGS credit posting",
      "Check if RTGS credit was posted to wrong account",
      "Verify account was active and not blocked during settlement",
      "Review RTGS inward processing log"
    ],
    "next_best_actions": [
      "Post RTGS credit in CBS if settlement confirmed",
      "Initiate return if account was blocked or closed",
      "Correct posting if credit was applied to wrong account",
      "Coordinate with originating bank for payment confirmation"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "IMPS Credit Not Received",
    "investigation_steps": [
      "Retrieve IMPS transaction reference number and check NPCI IMPS logs",
      "Verify CBS for incoming IMPS credit posting",
      "Check if IMPS credit was posted to wrong account",
      "Review account status at time of IMPS transaction"
    ],
    "next_best_actions": [
      "Post IMPS credit in CBS if NPCI records confirm successful transaction",
      "Initiate refund to sender if posting failed due to account issues",
      "Correct posting if credit applied to wrong account",
      "Coordinate with NPCI for IMPS transaction dispute resolution"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Fund Transfer Failed",
    "investigation_steps": [
      "Retrieve fund transfer request details and failure reason from CBS",
      "Check payment channel logs (NEFT/RTGS/IMPS) for failure reason code",
      "Verify beneficiary account details entered for the transfer",
      "Check if debit was made but credit failed (stuck in transit)"
    ],
    "next_best_actions": [
      "Initiate reversal of debit if funds are stuck in transit",
      "Retry fund transfer with correct beneficiary details",
      "Escalate to NPCI if funds are confirmed debited but not credited to beneficiary"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Fund Transfer Pending",
    "investigation_steps": [
      "Retrieve fund transfer status from CBS and payment channel",
      "Verify NEFT/RTGS/IMPS batch processing status",
      "Check if transfer is in queue or suspense in CBS",
      "Verify settlement cycle cut-off compliance"
    ],
    "next_best_actions": [
      "Process pending transfer from suspense queue",
      "Retry failed settlement batch for pending transfers",
      "Coordinate with NPCI for status confirmation if pending beyond settlement cycle"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Beneficiary Not Credited",
    "investigation_steps": [
      "Retrieve transfer details and verify credit to beneficiary account in CBS",
      "Check NEFT/RTGS/IMPS transaction status with NPCI",
      "Verify beneficiary bank's posting and acknowledgement",
      "Check if beneficiary account was blocked or closed"
    ],
    "next_best_actions": [
      "Initiate follow-up with beneficiary bank for credit confirmation",
      "Escalate to NPCI for inter-bank credit dispute",
      "Process reversal to sender if beneficiary bank confirms non-credit"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Beneficiary Added Incorrectly",
    "investigation_steps": [
      "Retrieve beneficiary details from CBS/internet banking system",
      "Verify beneficiary account number, IFSC, and name as added",
      "Check maker-checker log for beneficiary addition approval",
      "Verify if customer had authorized the beneficiary addition"
    ],
    "next_best_actions": [
      "Delete incorrect beneficiary record from CBS/internet banking system",
      "Re-add beneficiary with correct details",
      "Investigate if incorrect beneficiary addition was unauthorized and raise security alert"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Transaction Pending",
    "investigation_steps": [
      "Retrieve transaction details and status from CBS",
      "Check for pending batch processing or EOD queue",
      "Review payment channel logs for transaction state",
      "Check if transaction is in suspense or exception queue"
    ],
    "next_best_actions": [
      "Process transaction from suspense/exception queue",
      "Retry transaction if system error caused pending status",
      "Update CBS transaction status post resolution"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Transaction Reversed Incorrectly",
    "investigation_steps": [
      "Retrieve reversal transaction details from CBS",
      "Verify original transaction and reversal authorization",
      "Check if reversal was initiated by system, branch, or operations team",
      "Review reconciliation records and payment channel logs for the reversal"
    ],
    "next_best_actions": [
      "Re-credit customer account if reversal was applied incorrectly",
      "Reverse the erroneous reversal entry in CBS",
      "Obtain authorization and document corrective action"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Duplicate Transaction",
    "investigation_steps": [
      "Retrieve all transactions for the date and amount in CBS",
      "Verify switch/payment gateway logs for duplicate processing",
      "Check settlement records for duplicate debit/credit confirmation",
      "Review NPCI transaction logs for duplicate entry"
    ],
    "next_best_actions": [
      "Initiate reversal of duplicate transaction in CBS",
      "Reconcile with payment gateway/NPCI to confirm duplicate",
      "Credit customer account for duplicate debit amount"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Statement Not Available",
    "investigation_steps": [
      "Check statement generation system for the account and requested period",
      "Verify if account has sufficient transaction history in CBS",
      "Check internet banking/mobile banking statement module availability",
      "Review system downtime logs that may have caused statement unavailability"
    ],
    "next_best_actions": [
      "Generate account statement manually from CBS",
      "Dispatch statement via email or branch",
      "Escalate to IT if statement module is down"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Statement Download Failed",
    "investigation_steps": [
      "Check internet banking/mobile banking statement download module logs",
      "Verify PDF generation service status",
      "Check for browser/app compatibility issues causing failure",
      "Review server error logs for download endpoint"
    ],
    "next_best_actions": [
      "Escalate to IT to fix statement download module",
      "Generate and dispatch statement manually from CBS",
      "Provide alternate download link or format if available"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Passbook Not Updated",
    "investigation_steps": [
      "Verify if passbook printing machine at branch is operational",
      "Check CBS for pending transactions not yet reflected in passbook",
      "Verify if passbook account number matches CBS account"
    ],
    "next_best_actions": [
      "Update passbook at branch passbook printing kiosk",
      "Coordinate with branch to repair/replace passbook printer if faulty",
      "Issue new passbook if old one is damaged or full"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Passbook Printing Failed",
    "investigation_steps": [
      "Check passbook printer status and connectivity at branch",
      "Verify CBS connection to passbook printing system",
      "Review printing error logs from passbook printer"
    ],
    "next_best_actions": [
      "Repair or replace faulty passbook printer",
      "Provide printed account statement as interim solution",
      "Coordinate with IT to restore CBS-to-printer connectivity"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Mini Statement Incorrect",
    "investigation_steps": [
      "Retrieve last 5/10 transactions from CBS for comparison",
      "Check ATM switch logs for mini statement data feed",
      "Verify if CBS transaction data is correctly mapped to mini statement output"
    ],
    "next_best_actions": [
      "Correct data feed mapping between CBS and ATM switch",
      "Escalate to switch/IT team to fix mini statement generation",
      "Provide correct statement from CBS to customer via alternate channel"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Transaction History Missing",
    "investigation_steps": [
      "Retrieve full transaction history from CBS for the account",
      "Verify if missing transactions are present in CBS but not displaying in digital channel",
      "Check internet/mobile banking transaction history API logs",
      "Review if transactions were purged or archived"
    ],
    "next_best_actions": [
      "Restore transaction history display via API fix or data refresh",
      "Provide transaction history from CBS directly",
      "Escalate to IT if transactions are missing from CBS archives"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Transaction History Incorrect",
    "investigation_steps": [
      "Compare CBS transaction records with what is displayed in digital channel",
      "Check API/middleware data transformation logs for transaction history",
      "Verify if incorrect transaction data is due to display error or actual CBS mismatch"
    ],
    "next_best_actions": [
      "Correct API/middleware data mapping for transaction display",
      "Escalate to IT if CBS records themselves are incorrect",
      "Provide correct transaction details from CBS as interim"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Balance Not Updated",
    "investigation_steps": [
      "Check CBS for latest account balance and last update timestamp",
      "Verify if balance refresh is delayed in internet/mobile banking",
      "Check middleware/API cache for stale balance data",
      "Review EOD batch processing completion status"
    ],
    "next_best_actions": [
      "Trigger balance refresh in internet/mobile banking system",
      "Clear middleware cache to reflect updated balance",
      "Escalate to IT if balance update is not reflecting post EOD"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Summary Incorrect",
    "investigation_steps": [
      "Compare account summary displayed in digital channel with CBS data",
      "Check API response logs for account summary endpoint",
      "Verify if product or account type is incorrectly mapped in CBS"
    ],
    "next_best_actions": [
      "Correct account type/product mapping in CBS",
      "Fix API data mapping for account summary",
      "Escalate to IT for systemic corrections if needed"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "E-Statement Not Received",
    "investigation_steps": [
      "Verify registered email ID in CBS",
      "Check e-statement dispatch log for the period",
      "Verify email server delivery log for bounce or spam status",
      "Check if customer opted in for e-statement in CBS"
    ],
    "next_best_actions": [
      "Update correct email ID in CBS",
      "Re-dispatch e-statement to correct email ID",
      "Ensure e-statement opt-in is recorded in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Registered Mobile Number Not Updated",
    "investigation_steps": [
      "Retrieve current mobile number update request status from CBS",
      "Verify mobile number change request documentation submitted",
      "Check maker-checker workflow status in CBS for mobile update"
    ],
    "next_best_actions": [
      "Process mobile number update in CBS after verification",
      "Complete maker-checker approval for mobile number change",
      "Update mobile number across all linked systems (SMS, internet banking, card)"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Email ID Not Updated",
    "investigation_steps": [
      "Retrieve email update request status from CBS",
      "Verify email update request documentation and authorization",
      "Check maker-checker approval status for email change"
    ],
    "next_best_actions": [
      "Process email update in CBS after verification",
      "Confirm update across all linked digital channels",
      "Send confirmation of email update to new email ID"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Address Update Pending",
    "investigation_steps": [
      "Retrieve address update request and submitted proof of address from CBS",
      "Check maker-checker workflow status for address change",
      "Verify KYC compliance for new address document"
    ],
    "next_best_actions": [
      "Process address update in CBS after document verification",
      "Complete maker-checker approval",
      "Update CKYC with revised address",
      "Trigger re-dispatch of physical communication to updated address"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Name Correction Pending",
    "investigation_steps": [
      "Retrieve name correction request and supporting documents from CBS",
      "Verify name in KYC documents (PAN, Aadhaar, passport)",
      "Check maker-checker workflow status for name correction",
      "Verify legal/official document supporting the name change"
    ],
    "next_best_actions": [
      "Process name correction in CBS after document verification",
      "Update CKYC records with corrected name",
      "Update all linked products (card, internet banking) with corrected name",
      "Issue revised documents (cheque book, card) with corrected name if required"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Nominee Addition Pending",
    "investigation_steps": [
      "Retrieve nominee addition request and Form DA1 from CBS",
      "Check maker-checker workflow status for nominee update",
      "Verify nominee details in submitted form"
    ],
    "next_best_actions": [
      "Process nominee addition in CBS after verification",
      "Complete maker-checker approval",
      "Update CBS with nominee details and issue acknowledgement"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Nominee Update Pending",
    "investigation_steps": [
      "Retrieve nominee update request and Form DA2 from CBS",
      "Check maker-checker workflow status",
      "Verify existing nominee record in CBS"
    ],
    "next_best_actions": [
      "Process nominee update in CBS after verification",
      "Complete maker-checker approval",
      "Replace old nominee record with updated details in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Nominee Removal Pending",
    "investigation_steps": [
      "Retrieve nominee removal request and Form DA3 from CBS",
      "Check maker-checker workflow status",
      "Verify existing nominee record in CBS"
    ],
    "next_best_actions": [
      "Process nominee removal in CBS after verification",
      "Complete maker-checker approval",
      "Remove nominee record from CBS and issue acknowledgement"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "PAN Update Failed",
    "investigation_steps": [
      "Retrieve PAN update request and submitted PAN card copy from CBS",
      "Check maker-checker workflow status for PAN update",
      "Verify PAN number validity with NSDL/UTIITSL database",
      "Check if PAN is already linked to another CIF"
    ],
    "next_best_actions": [
      "Update PAN in CBS after verification",
      "Resolve duplicate PAN mapping if PAN is linked to multiple CIFs",
      "Update CKYC with PAN details",
      "Ensure TDS configuration is updated post PAN linkage"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Aadhaar Update Failed",
    "investigation_steps": [
      "Retrieve Aadhaar update request and submitted document from CBS",
      "Check UIDAI seeding status in CBS",
      "Verify Aadhaar number validity with UIDAI",
      "Check if Aadhaar is already linked to another account/CIF",
      "Check NPCI mapper linkage status for DBT"
    ],
    "next_best_actions": [
      "Complete Aadhaar seeding in CBS after UIDAI verification",
      "Update NPCI mapper for DBT linkage",
      "Resolve duplicate Aadhaar-account linkage if applicable",
      "Update CKYC with Aadhaar details"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "KYC Verification Pending",
    "investigation_steps": [
      "Retrieve KYC documents submitted and verification queue status",
      "Check KYC verification system for pending items",
      "Verify if all required KYC documents are present and legible",
      "Check if third-party verification (UIDAI/NSDL) response is awaited"
    ],
    "next_best_actions": [
      "Complete KYC document verification in system",
      "Obtain additional or clearer documents if required",
      "Update KYC status in CBS upon completion",
      "Trigger CKYC upload post KYC completion"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "KYC Status Not Updated",
    "investigation_steps": [
      "Verify KYC completion status in KYC verification system",
      "Check if KYC status has been updated in CBS",
      "Review CBS-KYC system integration logs",
      "Verify CKYC upload status on CKYC registry"
    ],
    "next_best_actions": [
      "Manually update KYC status in CBS",
      "Trigger CKYC upload if pending",
      "Resolve integration issue between KYC system and CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Video KYC Failed",
    "investigation_steps": [
      "Retrieve video KYC session logs and failure reason",
      "Check if failure was due to network, document quality, or facial match",
      "Verify auditor/bank officer action during video KYC session",
      "Check RBI video KYC compliance requirements against session"
    ],
    "next_best_actions": [
      "Reschedule video KYC session after resolving failure cause",
      "Conduct in-branch KYC if video KYC repeatedly fails",
      "Update KYC status in CBS post successful re-verification",
      "Provide customer with alternative KYC channel instructions"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "CKYC Not Updated",
    "investigation_steps": [
      "Retrieve CKYC upload status from CKYC registry portal",
      "Check CBS for CKYC number linkage",
      "Review CKYC upload file and response from CERSAI",
      "Verify KYC documents for CKYC compliance"
    ],
    "next_best_actions": [
      "Re-upload CKYC record to CERSAI registry",
      "Correct data errors in CKYC upload file",
      "Link CKYC number to CBS account upon successful upload"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Conversion Pending",
    "investigation_steps": [
      "Retrieve account conversion request from CBS",
      "Verify eligibility for conversion (e.g., regular to salary, basic to premium)",
      "Check maker-checker workflow status for conversion",
      "Verify all required documentation for new account type"
    ],
    "next_best_actions": [
      "Process account conversion in CBS",
      "Update product parameters, fee schedule, and limits per new account type",
      "Complete maker-checker approval",
      "Notify linked systems of account type change"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Joint Holder Addition Pending",
    "investigation_steps": [
      "Retrieve joint holder addition request and submitted documents from CBS",
      "Verify KYC status of new joint holder",
      "Check maker-checker workflow status for joint holder addition"
    ],
    "next_best_actions": [
      "Complete KYC of new joint holder",
      "Process joint holder addition in CBS",
      "Update operating instructions and account mandate in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Joint Holder Removal Pending",
    "investigation_steps": [
      "Retrieve joint holder removal request and authorization documentation from CBS",
      "Verify consent of all account holders for removal",
      "Check maker-checker workflow status"
    ],
    "next_best_actions": [
      "Process joint holder removal in CBS after consent verification",
      "Update account operating instructions in CBS",
      "Issue revised account documentation if required"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Signature Update Pending",
    "investigation_steps": [
      "Retrieve signature update request and new specimen signature card",
      "Check maker-checker workflow status in CBS",
      "Verify identity of customer submitting signature update"
    ],
    "next_best_actions": [
      "Update specimen signature in CBS after verification",
      "Complete maker-checker approval",
      "Archive old signature record in CBS"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Photo Update Pending",
    "investigation_steps": [
      "Retrieve photo update request and new photograph submitted",
      "Check maker-checker workflow status in CBS",
      "Verify identity of customer submitting photo update"
    ],
    "next_best_actions": [
      "Update customer photo in CBS after verification",
      "Complete maker-checker approval",
      "Update photo in all linked systems"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Date of Birth Correction Pending",
    "investigation_steps": [
      "Retrieve date of birth correction request and supporting KYC document",
      "Verify DOB in PAN/Aadhaar/passport submitted",
      "Check maker-checker workflow status in CBS"
    ],
    "next_best_actions": [
      "Correct date of birth in CBS after document verification",
      "Update CKYC records with corrected DOB",
      "Complete maker-checker approval"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Customer ID Mapping Incorrect",
    "investigation_steps": [
      "Retrieve customer ID (CIF) and linked accounts from CBS",
      "Verify if accounts are incorrectly mapped to wrong CIF",
      "Check CIF deduplication records",
      "Review account creation logs for mapping errors"
    ],
    "next_best_actions": [
      "Correct CIF-to-account mapping in CBS",
      "Merge duplicate CIFs if deduplication identifies multiple records",
      "Update all linked products to correct CIF",
      "Escalate to CBS admin team for CIF correction"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Closure Delay",
    "investigation_steps": [
      "Retrieve account closure request status from CBS",
      "Check for pending transactions, lien, or standing instructions on account",
      "Verify if all linked products (cards, loans, mandates) are closed/cancelled",
      "Review branch processing queue for closure request"
    ],
    "next_best_actions": [
      "Resolve pending transactions and liens before processing closure",
      "Cancel linked mandates and standing instructions",
      "Process account closure in CBS after all prerequisites are met"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Closure Not Processed",
    "investigation_steps": [
      "Retrieve closure request from CBS and verify submission date",
      "Check for any open items preventing closure (lien, linked loan, active mandate)",
      "Review closure request workflow in CBS for incomplete steps"
    ],
    "next_best_actions": [
      "Resolve all open items blocking closure",
      "Process account closure in CBS",
      "Return remaining balance to customer via NEFT/cheque",
      "Issue closure confirmation to customer"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Closed Account Still Active",
    "investigation_steps": [
      "Check CBS for account closure completion status",
      "Verify if closure request was processed but CBS status not updated",
      "Review closure processing log for errors",
      "Check if account appears active in any linked systems"
    ],
    "next_best_actions": [
      "Update account status to Closed in CBS",
      "Ensure debit and credit blocks are applied on the account",
      "Reconcile and remove account from active account reports"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Closure Request Rejected",
    "investigation_steps": [
      "Retrieve closure rejection reason code from CBS",
      "Check for outstanding dues, negative balance, or linked liabilities",
      "Verify if closure was rejected due to regulatory or legal hold",
      "Review maker-checker rejection notes"
    ],
    "next_best_actions": [
      "Communicate specific rejection reason to operations team",
      "Resolve underlying issues (clear dues, remove hold) and reprocess closure",
      "Escalate to legal/compliance if regulatory hold is unjustified"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Closure Confirmation Not Received",
    "investigation_steps": [
      "Verify if account closure was completed in CBS",
      "Check dispatch log for closure confirmation letter or email",
      "Verify registered email/address in CBS for confirmation dispatch"
    ],
    "next_best_actions": [
      "Re-dispatch closure confirmation via email or physical letter",
      "Update correct contact details in CBS if dispatch failed due to incorrect details",
      "Generate and share closure confirmation from CBS records"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "No Dues Certificate Not Issued",
    "investigation_steps": [
      "Verify account closure completion status in CBS",
      "Check for pending dues or liabilities on the account",
      "Review no dues certificate generation process in system"
    ],
    "next_best_actions": [
      "Issue No Dues Certificate from CBS upon confirming zero balance and closure",
      "Settle any pending dues and then issue certificate",
      "Dispatch certificate to customer via registered email or courier"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Remaining Balance Not Refunded",
    "investigation_steps": [
      "Verify account closure completion and remaining balance in CBS",
      "Check if refund was initiated via NEFT, cheque, or cash",
      "Retrieve refund transaction status from CBS",
      "Verify refund beneficiary details used for NEFT"
    ],
    "next_best_actions": [
      "Initiate NEFT or demand draft for remaining balance",
      "Process refund from CBS with proper GL entries",
      "Confirm refund credit with customer after processing"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Closure Charges Incorrect",
    "investigation_steps": [
      "Retrieve account closure charge details from CBS",
      "Verify applicable closure charge as per fee schedule and account type",
      "Check if account closure is within the minimum tenure for closure charges"
    ],
    "next_best_actions": [
      "Reverse incorrect closure charge in CBS",
      "Apply correct closure charge as per approved fee schedule",
      "Refund differential amount to customer"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Closure Request Pending",
    "investigation_steps": [
      "Retrieve closure request status and submission timestamp from CBS",
      "Check for any pending prerequisites (lien removal, mandate cancellation)",
      "Review branch processing queue for pending closure requests"
    ],
    "next_best_actions": [
      "Expedite processing of pending closure request",
      "Resolve blocking prerequisites and process closure in CBS",
      "Update closure request status in system"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Account Reopened Without Consent",
    "investigation_steps": [
      "Check CBS for account reactivation log and initiating officer/channel",
      "Review audit trail for reopen request and authorization",
      "Check if reopen was triggered by system batch (e.g., government credit)",
      "Verify if any transaction was credited after closure triggering reopen"
    ],
    "next_best_actions": [
      "Re-close the account in CBS if reopening was unauthorized",
      "Initiate investigation against initiating officer if manual reopen",
      "Return any credits received post unauthorized reopen to sender",
      "Document incident and escalate to internal audit if fraud suspected"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "SMS Alerts Not Received",
    "investigation_steps": [
      "Verify registered mobile number in CBS",
      "Check SMS service provider dispatch logs for the account",
      "Verify SMS alert subscription status in CBS",
      "Check if mobile number is on DND (Do Not Disturb) registry"
    ],
    "next_best_actions": [
      "Update correct mobile number in CBS",
      "Reactivate SMS alert subscription if deactivated",
      "Coordinate with SMS service provider to resolve delivery failure",
      "Check DND status and whitelist bank's sender ID if required"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Email Alerts Not Received",
    "investigation_steps": [
      "Verify registered email ID in CBS",
      "Check email dispatch logs for the account",
      "Verify email alert subscription status in CBS",
      "Check for email bounce or spam filter blocking bank emails"
    ],
    "next_best_actions": [
      "Update correct email ID in CBS",
      "Reactivate email alert subscription if deactivated",
      "Coordinate with email service provider to resolve delivery failure",
      "Request customer to whitelist bank's email domain"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Push Notifications Not Received",
    "investigation_steps": [
      "Verify mobile banking app registration and notification permission status",
      "Check push notification service logs for the customer's device",
      "Verify if customer's device token is registered in notification server",
      "Check app version compatibility with push notification service"
    ],
    "next_best_actions": [
      "Re-register device token in push notification server",
      "Request customer to re-install or update mobile banking app",
      "Escalate to IT/app team if push notification service is down"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "OTP Not Received",
    "investigation_steps": [
      "Verify registered mobile number in CBS",
      "Check OTP dispatch logs from OTP gateway for the transaction",
      "Verify if mobile number is on DND registry",
      "Check SMS gateway delivery status and error codes"
    ],
    "next_best_actions": [
      "Update correct mobile number in CBS",
      "Coordinate with SMS gateway provider to resolve delivery failure",
      "Whitelist bank's sender ID for OTP delivery",
      "Provide alternate OTP channel (email OTP) if supported"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Unauthorized Login Attempt",
    "investigation_steps": [
      "Retrieve internet/mobile banking login attempt logs for the account",
      "Identify source IP, device, and timestamp of unauthorized attempt",
      "Check if account was accessed or locked post failed attempts",
      "Review fraud detection system alerts for the account"
    ],
    "next_best_actions": [
      "Lock internet banking account pending investigation",
      "Reset credentials and notify account holder",
      "Escalate to cyber security/fraud team",
      "Log security incident and monitor account for suspicious activity"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Fraudulent Transaction",
    "investigation_steps": [
      "Retrieve transaction details and channel logs (ATM, POS, online, IMPS)",
      "Verify if customer authorized the transaction",
      "Review fraud detection system alerts and risk scores",
      "Check card management system for card status and usage",
      "Verify geolocation and device fingerprint of transaction"
    ],
    "next_best_actions": [
      "Block card and internet banking access immediately",
      "Initiate chargeback or dispute process",
      "Process provisional credit as per RBI fraud liability guidelines",
      "File fraud report and escalate to cyber crime cell",
      "Coordinate with NPCI for transaction dispute"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Suspicious Account Activity",
    "investigation_steps": [
      "Retrieve transaction history for the account for the flagged period",
      "Review AML/fraud detection system alerts and risk scores",
      "Identify unusual transaction patterns (frequency, amount, geography)",
      "Check KYC profile against transaction behavior"
    ],
    "next_best_actions": [
      "Place account under enhanced monitoring in CBS",
      "Escalate to compliance/AML team for review",
      "Apply transaction restrictions if risk threshold exceeded",
      "File Suspicious Transaction Report (STR) with FIU-IND if warranted"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Complaint Resolution Delay",
    "investigation_steps": [
      "Retrieve complaint details and submission timestamp from CRM system",
      "Check current status and ownership of complaint in CRM",
      "Review escalation history and pending actions in complaint log",
      "Identify bottleneck in resolution workflow"
    ],
    "next_best_actions": [
      "Reassign complaint to appropriate team for immediate resolution",
      "Escalate to senior operations management if SLA is breached",
      "Update CRM with resolution action and expected closure date",
      "Ensure regulatory timelines per RBI grievance redressal guidelines are met"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Service Request Pending",
    "investigation_steps": [
      "Retrieve service request details and submission date from CRM",
      "Check current processing status and assigned team",
      "Identify any pending documentation or approvals blocking the request"
    ],
    "next_best_actions": [
      "Prioritize and process pending service request",
      "Obtain missing documentation or approvals",
      "Update CRM with resolution action and closure date"
    ]
  },
  {
    "major_issue": "Savings Account",
    "sub_issue": "Branch Not Responding",
    "investigation_steps": [
      "Verify branch contact details and operating hours in system",
      "Check if complaint/query was logged with branch and assigned",
      "Review branch service request queue for pending items",
      "Escalate to regional banking office if branch is unreachable"
    ],
    "next_best_actions": [
      "Escalate complaint to regional/zonal office for resolution",
      "Assign to alternate branch or central ops team for processing",
      "Update CRM with escalation details and alternate point of contact"
    ]
  }
],
[
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Book Request Failed",
    "investigation_steps": [
      "Retrieve cheque book request log from CBS for the account",
      "Check CBS error code returned at time of request failure",
      "Verify account status and eligibility for cheque book issuance",
      "Check if account has active debit block or restriction preventing issuance",
      "Review CTS-compliant cheque book inventory availability at branch/central processing"
    ],
    "next_best_actions": [
      "Resolve account restriction or debit block preventing cheque book request",
      "Re-raise cheque book request in CBS after fixing root cause",
      "Coordinate with branch/central ops to manually initiate cheque book order",
      "Update request status in CBS"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Book Not Received",
    "investigation_steps": [
      "Verify cheque book dispatch status in CBS and courier tracking system",
      "Check courier/speed post tracking number and delivery confirmation",
      "Verify registered address in CBS against dispatch address used",
      "Check if cheque book was returned undelivered to bank"
    ],
    "next_best_actions": [
      "Initiate re-dispatch of cheque book to verified address",
      "Update address in CBS if mismatch caused non-delivery",
      "Coordinate with courier partner to trace undelivered cheque book",
      "Raise fresh cheque book request in CBS if original is confirmed lost in transit"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Book Delivery Delayed",
    "investigation_steps": [
      "Check cheque book dispatch date and courier tracking status",
      "Verify if delay is at printing, dispatch, or courier leg",
      "Confirm cheque book printing completion at central stationery unit",
      "Review courier partner SLA adherence for the dispatch date"
    ],
    "next_best_actions": [
      "Escalate delivery delay to courier partner for expedited delivery",
      "Coordinate with central stationery unit if printing is pending",
      "Provide interim cheque leaves at branch if delivery is critically delayed"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Book Sent to Wrong Address",
    "investigation_steps": [
      "Retrieve dispatch address used from courier manifest",
      "Compare dispatch address with registered address in CBS",
      "Check if address error was in CBS records or in dispatch system mapping",
      "Verify if cheque book was delivered and received at wrong address"
    ],
    "next_best_actions": [
      "Initiate cheque book recall from wrong address if feasible",
      "Hot-list the dispatched cheque series in CBS to prevent misuse",
      "Issue replacement cheque book and dispatch to correct address",
      "Correct address in CBS if input error identified"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Book Pages Missing",
    "investigation_steps": [
      "Retrieve cheque book issuance record and number of leaves issued in CBS",
      "Check central stationery/printing unit records for leaf count at dispatch",
      "Verify if shortage was reported at time of receipt",
      "Review courier handling record for tampering evidence"
    ],
    "next_best_actions": [
      "Hot-list missing leaf series in CBS to prevent misuse",
      "Issue replacement leaves or fresh cheque book",
      "Escalate to stationery/printing unit for quality check",
      "Log incident with courier partner if tampering is suspected"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Book Printed Incorrectly",
    "investigation_steps": [
      "Retrieve cheque book issuance record and printing data from CBS",
      "Compare printed details (name, account number, MICR code, IFSC) against CBS records",
      "Check if printing error is in CBS data or at stationery/printing unit",
      "Verify MICR band accuracy on affected cheque book"
    ],
    "next_best_actions": [
      "Hot-list incorrectly printed cheque book series in CBS",
      "Initiate fresh cheque book request with correct details",
      "Escalate printing error to stationery/printing unit for quality correction",
      "Update CBS records if incorrect data in CBS caused the print error"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Book Lost in Transit",
    "investigation_steps": [
      "Check courier tracking for last known status of shipment",
      "Verify if cheque book is confirmed lost by courier partner",
      "Retrieve dispatched cheque leaf series range from CBS dispatch record"
    ],
    "next_best_actions": [
      "Hot-list entire lost cheque leaf series in CBS immediately",
      "File courier loss claim with the logistics partner",
      "Issue replacement cheque book and dispatch via alternate courier",
      "Update CBS with hot-list and replacement details"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Book Request Rejected",
    "investigation_steps": [
      "Retrieve rejection reason code from CBS for the cheque book request",
      "Check account status, KYC compliance, and eligibility for cheque book",
      "Verify if rejection was due to account type restriction or risk flag",
      "Review internal policy on cheque book issuance eligibility"
    ],
    "next_best_actions": [
      "Resolve underlying reason for rejection (KYC, account status, risk flag)",
      "Reprocess cheque book request in CBS after resolution",
      "Escalate to risk or compliance team if rejection flag is erroneous"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Additional Cheque Book Not Issued",
    "investigation_steps": [
      "Check if additional cheque book request was raised in CBS",
      "Verify account eligibility for additional cheque book under product terms",
      "Check if previous cheque book series is exhausted as per CBS records",
      "Review branch or central ops processing queue for pending request"
    ],
    "next_best_actions": [
      "Process additional cheque book request in CBS",
      "Verify eligibility and approve additional issuance",
      "Dispatch additional cheque book to registered address"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Personalized Cheque Book Delay",
    "investigation_steps": [
      "Check personalized cheque book order status at stationery/printing unit",
      "Verify order submission date and expected delivery timeline",
      "Review courier dispatch status for personalized cheque book",
      "Check if personalization data (name, logo) was submitted correctly"
    ],
    "next_best_actions": [
      "Escalate order to stationery unit for expedited printing",
      "Verify and correct personalization data if error found",
      "Coordinate courier dispatch on priority after printing completion"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Deposit Failed",
    "investigation_steps": [
      "Retrieve cheque deposit transaction details from CBS",
      "Check CTS clearing system for deposit submission status",
      "Verify if failure was due to account restriction, MICR error, or system downtime",
      "Check branch teller system logs for deposit failure event"
    ],
    "next_best_actions": [
      "Resolve account restriction and re-present cheque for clearing",
      "Correct MICR data if encoding error is identified",
      "Resubmit cheque deposit through CTS after fixing root cause"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Deposit Pending",
    "investigation_steps": [
      "Check CBS and CTS clearing queue for cheque deposit status",
      "Verify if cheque was submitted to CTS grid within clearing cut-off time",
      "Review branch batch processing logs for pending deposit"
    ],
    "next_best_actions": [
      "Submit cheque to CTS clearing in next available batch",
      "Process pending deposit from branch queue",
      "Update CBS with deposit submission status"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Deposited but Not Credited",
    "investigation_steps": [
      "Retrieve cheque deposit acknowledgement and CTS clearing records",
      "Verify if cheque was cleared in CTS grid and settlement received",
      "Check CBS for inward clearing credit posting",
      "Verify if credit was posted to correct account number"
    ],
    "next_best_actions": [
      "Post credit in CBS if CTS settlement is confirmed",
      "Correct posting if credit applied to wrong account",
      "Reconcile CTS settlement records with CBS credits"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Cleared but Amount Not Credited",
    "investigation_steps": [
      "Verify CTS clearing confirmation and settlement amount",
      "Check CBS inward clearing posting records",
      "Verify account number and MICR details used for credit posting",
      "Review reconciliation records for the clearing date"
    ],
    "next_best_actions": [
      "Post credit in CBS after confirming clearing settlement",
      "Correct posting to right account if MICR mismatch caused wrong credit",
      "Escalate to clearing reconciliation team for settlement adjustment"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Returned Without Reason",
    "investigation_steps": [
      "Retrieve cheque return record from CTS clearing system",
      "Verify return reason code issued by drawee bank",
      "Check if return memo was generated and dispatched",
      "Review if cheque return was triggered by CTS system or drawee bank"
    ],
    "next_best_actions": [
      "Obtain return reason code from drawee bank via CTS grid",
      "Issue formal cheque return memo with reason code to customer",
      "Update CBS with correct return reason"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Bounced Incorrectly",
    "investigation_steps": [
      "Retrieve drawee account balance at time of cheque presentation from CBS",
      "Check CTS return record and return reason code applied",
      "Verify if return was triggered by system error, MICR error, or incorrect account status",
      "Review drawee bank's return advice"
    ],
    "next_best_actions": [
      "Reverse cheque return and re-present cheque if erroneous return is confirmed",
      "Correct MICR or account data if technical error caused bounce",
      "Reimburse cheque bounce charges if bounce was due to bank error",
      "Update CBS and clear incorrect return record"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Clearing Delayed",
    "investigation_steps": [
      "Check CTS clearing grid status for the cheque and clearing date",
      "Verify if cheque was submitted within clearing cut-off time",
      "Review NPCI/RBI clearing grid schedule for delays on the clearing date",
      "Check branch batch submission timestamp"
    ],
    "next_best_actions": [
      "Resubmit cheque to next CTS clearing cycle if missed cut-off",
      "Escalate to NPCI clearing team if grid-level delay is identified",
      "Update CBS with revised expected credit date"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Collection Delayed",
    "investigation_steps": [
      "Retrieve cheque collection request details from CBS",
      "Check collection agent or correspondent bank processing status",
      "Verify if cheque was dispatched to drawee bank location for collection",
      "Review outstation cheque collection processing timeline"
    ],
    "next_best_actions": [
      "Follow up with collection agent or correspondent bank for status",
      "Escalate to outward collection team for expedited processing",
      "Update CBS with collection status and revised credit timeline"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Sent for Collection but Not Updated",
    "investigation_steps": [
      "Retrieve collection dispatch record from CBS",
      "Check collection agent acknowledgement and processing status",
      "Verify if status update from drawee bank or correspondent bank is pending",
      "Review CBS outward collection module for status update lag"
    ],
    "next_best_actions": [
      "Follow up with collection agent for status confirmation",
      "Manually update CBS with collection progress status",
      "Escalate to outward collection team to obtain and update status"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Deposit Receipt Not Generated",
    "investigation_steps": [
      "Check branch teller system for deposit transaction and receipt generation log",
      "Verify if CBS deposit entry was created without receipt output",
      "Check teller printer status and receipt printing log at branch"
    ],
    "next_best_actions": [
      "Generate duplicate deposit receipt from CBS transaction record",
      "Repair or replace teller receipt printer if hardware failure identified",
      "Issue manual deposit acknowledgement from branch if system receipt unavailable"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "CTS Clearing Delay",
    "investigation_steps": [
      "Check NPCI CTS grid processing status for the affected clearing date",
      "Verify bank's CTS outward batch submission timestamp",
      "Review RBI/NPCI clearing schedule and any announced grid disruptions",
      "Check if delay is at bank's CTS node or at NPCI central clearing"
    ],
    "next_best_actions": [
      "Escalate to NPCI CTS operations team for grid-level delay resolution",
      "Resubmit affected batch if bank-side submission error is identified",
      "Update CBS with revised clearing and credit timeline"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "CTS Image Not Available",
    "investigation_steps": [
      "Retrieve CTS image capture log for the cheque",
      "Check CTS scanning system for image storage and retrieval status",
      "Verify if image was captured but failed to upload to CTS grid",
      "Check CTS image archive for the cheque reference"
    ],
    "next_best_actions": [
      "Re-scan cheque and upload image to CTS grid",
      "Retrieve archived CTS image from backup if original is missing",
      "Escalate to IT/CTS operations team to restore image availability"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Truncation Failed",
    "investigation_steps": [
      "Check CTS scanning and truncation system logs for failure event",
      "Verify MICR code readability on the cheque",
      "Review CTS node connectivity and processing status",
      "Check if truncation failed at bank node or NPCI grid"
    ],
    "next_best_actions": [
      "Re-present cheque for truncation after resolving MICR or connectivity issue",
      "Manually encode MICR data if reader error caused failure",
      "Escalate CTS node issue to IT/NPCI operations team"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "CTS Verification Failed",
    "investigation_steps": [
      "Retrieve CTS verification failure reason from CTS system",
      "Check if failure was due to image quality, MICR mismatch, or data validation error",
      "Verify cheque details against MICR band data",
      "Review drawee bank's response to CTS verification query"
    ],
    "next_best_actions": [
      "Re-scan cheque with higher resolution if image quality caused failure",
      "Correct MICR data encoding if mismatch identified",
      "Resubmit cheque for CTS verification after resolving root cause"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Scanning Error",
    "investigation_steps": [
      "Retrieve scanning error log from CTS scanning system",
      "Check scanner hardware status and calibration at branch/processing centre",
      "Verify if error was due to cheque physical condition (torn, folded, ink smear)",
      "Review CTS image output for the affected cheque"
    ],
    "next_best_actions": [
      "Recalibrate or repair CTS scanner",
      "Re-scan cheque under correct conditions",
      "Process cheque through alternate CTS-enabled branch if scanner is non-functional"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Image Mismatch",
    "investigation_steps": [
      "Retrieve CTS image and compare front and rear image against physical cheque",
      "Verify if mismatch is due to incorrect image pairing in CTS system",
      "Check CTS image capture sequence log at scanning station",
      "Review NPCI CTS grid for image data integrity"
    ],
    "next_best_actions": [
      "Re-scan and re-upload correct cheque image to CTS grid",
      "Correct image pairing in CTS system if sequencing error identified",
      "Escalate to IT/NPCI to correct image data in clearing system"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Signature Verification Failed",
    "investigation_steps": [
      "Retrieve specimen signature from CBS for comparison",
      "Review CTS image of cheque signature against CBS specimen",
      "Verify if signature verification was automated or manual",
      "Check if specimen signature in CBS is current and up to date"
    ],
    "next_best_actions": [
      "Conduct manual signature verification by authorized officer",
      "Update specimen signature in CBS if outdated signature caused mismatch",
      "Return cheque with correct return code if signature is genuinely mismatched",
      "Honour cheque after manual verification if signature is valid"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Signature Mismatch Reported Incorrectly",
    "investigation_steps": [
      "Retrieve CTS cheque image and compare with CBS specimen signature",
      "Verify if signature mismatch was flagged by automated system or manual review",
      "Check if specimen signature in CBS is outdated",
      "Review authorization record for the cheque return decision"
    ],
    "next_best_actions": [
      "Reverse cheque return if manual verification confirms signature is valid",
      "Update specimen signature in CBS with customer's current signature",
      "Reimburse cheque return charges if return was due to bank error",
      "Re-present cheque for payment after corrective action"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Processing Error",
    "investigation_steps": [
      "Retrieve cheque processing error log from CBS and CTS system",
      "Identify error type: data entry, MICR read, account posting, or clearing module error",
      "Verify cheque details against CBS account records",
      "Check CTS grid acknowledgement for the cheque"
    ],
    "next_best_actions": [
      "Correct identified processing error in CBS",
      "Reprocess cheque through CTS clearing after correction",
      "Update CBS with corrected transaction details"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Validation Failed",
    "investigation_steps": [
      "Retrieve validation failure reason from CBS or CTS system",
      "Verify cheque validity period, account number, MICR code, and amount in words vs figures",
      "Check if validation failure was due to system rule or genuine instrument defect",
      "Review drawee bank's validation response"
    ],
    "next_best_actions": [
      "Correct data entry error and revalidate if validation failure is system-generated",
      "Return cheque with correct return code if instrument defect is confirmed",
      "Escalate to CTS operations team if validation rule is incorrectly configured"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Post-Dated Cheque Presented Early",
    "investigation_steps": [
      "Retrieve cheque date and presentation date from CBS and CTS records",
      "Verify if post-dated status was flagged during deposit or CTS submission",
      "Check teller or CTS scanning system logs for date validation at deposit",
      "Review CBS rules for post-dated cheque handling"
    ],
    "next_best_actions": [
      "Recall cheque from CTS clearing if presented before cheque date",
      "Hold cheque in CBS until the instrument date and re-present on due date",
      "Reverse any debit or credit posted due to early presentation",
      "Strengthen teller controls for post-dated cheque identification"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Post-Dated Cheque Not Presented",
    "investigation_steps": [
      "Retrieve post-dated cheque holding record from CBS",
      "Check if presentation was scheduled and missed in the system",
      "Verify if cheque was returned, lost, or misplaced at branch",
      "Review branch post-dated cheque register"
    ],
    "next_best_actions": [
      "Present cheque immediately if instrument date has passed",
      "Locate and present cheque if misplaced at branch",
      "Update CBS with presentation action and outcome"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Stale Cheque Rejected Incorrectly",
    "investigation_steps": [
      "Retrieve cheque date and presentation date from CTS records",
      "Calculate validity period as per RBI guidelines (3 months from date of instrument)",
      "Verify if rejection was applied within or outside the validity period",
      "Review CTS or CBS system date validation rule for stale cheque"
    ],
    "next_best_actions": [
      "Re-present cheque if rejection was applied erroneously within validity period",
      "Correct stale cheque date validation rule in CTS system if system error identified",
      "Update CBS and remove erroneous return record"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Future-Dated Cheque Rejected",
    "investigation_steps": [
      "Retrieve cheque date and rejection details from CBS or CTS system",
      "Verify if future date was a genuine instrument date or data entry error",
      "Check teller processing log for cheque acceptance validation"
    ],
    "next_best_actions": [
      "Hold cheque in CBS if instrument date is genuine and future-dated",
      "Correct data entry error if date was incorrectly captured",
      "Re-present cheque on the instrument date"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Validity Dispute",
    "investigation_steps": [
      "Retrieve cheque instrument date and presentation date",
      "Apply RBI validity guidelines (3 months) to determine instrument validity",
      "Review any special terms on the instrument (e.g., valid for 6 months)",
      "Check drawee bank's response on validity dispute"
    ],
    "next_best_actions": [
      "Re-present cheque within valid period if dispute is due to incorrect rejection",
      "Return cheque with correct return reason if instrument is genuinely stale",
      "Escalate to clearing operations team for resolution"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Presented Multiple Times",
    "investigation_steps": [
      "Retrieve all presentation records for the cheque number from CTS and CBS",
      "Verify if multiple presentations were made across different clearing cycles or branches",
      "Check NPCI CTS grid for duplicate presentation detection",
      "Identify which presentation resulted in payment"
    ],
    "next_best_actions": [
      "Reject duplicate presentation in CTS if cheque is already paid",
      "Reverse duplicate credit if beneficiary was credited multiple times",
      "Update CBS and CTS records to prevent further duplicate presentation",
      "Investigate and flag source of duplicate presentation"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Duplicate Cheque Clearing",
    "investigation_steps": [
      "Retrieve CTS records for both clearing instances of the same cheque",
      "Check NPCI CTS duplicate detection logs",
      "Verify settlement records for both clearing instances",
      "Identify if duplicate clearing resulted in double payment"
    ],
    "next_best_actions": [
      "Initiate reversal of duplicate clearing entry in CBS",
      "Coordinate with NPCI CTS operations to cancel duplicate settlement",
      "Recover duplicate payment amount from beneficiary account",
      "Escalate to reconciliation team for settlement correction"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Paid Twice",
    "investigation_steps": [
      "Retrieve both payment records for the cheque from CBS",
      "Verify if second payment was due to duplicate CTS clearing or teller error",
      "Check drawee account debit records for double debit",
      "Review NPCI CTS settlement for duplicate payment confirmation"
    ],
    "next_best_actions": [
      "Reverse second payment entry in CBS",
      "Recover duplicate payment from beneficiary account",
      "Coordinate with NPCI/CTS for settlement correction",
      "Credit drawee account for duplicate debit"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Cleared Despite Stop Payment",
    "investigation_steps": [
      "Retrieve stop payment instruction record from CBS and verify its status",
      "Check if stop payment was active at time of cheque presentation in CTS",
      "Review CTS clearing system's stop payment validation check",
      "Verify if stop payment was applied to the correct cheque number and account"
    ],
    "next_best_actions": [
      "Initiate reversal of payment and recover funds from beneficiary account",
      "Credit drawee account for the erroneously cleared cheque amount",
      "Investigate failure of stop payment validation in CTS integration",
      "Escalate to IT to fix stop payment check in CTS clearing workflow"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Not Presented to Bank",
    "investigation_steps": [
      "Retrieve cheque deposit or collection request record from CBS",
      "Verify if cheque was received by branch and logged",
      "Check branch cheque register and teller records for the cheque",
      "Trace cheque through inward collection or deposit processing chain"
    ],
    "next_best_actions": [
      "Locate cheque at branch or collection centre and initiate presentation",
      "Escalate to branch operations manager if cheque is missing",
      "File internal inquiry if cheque cannot be traced",
      "Issue duplicate instrument or take appropriate customer corrective action"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Stop Payment Request Failed",
    "investigation_steps": [
      "Retrieve stop payment request log from CBS",
      "Check CBS error code returned at time of stop payment failure",
      "Verify if request was made for a valid cheque number within the active series",
      "Check if account status or cheque series eligibility prevented stop payment"
    ],
    "next_best_actions": [
      "Re-raise stop payment request in CBS after resolving error",
      "Correct cheque number or series details if data entry error caused failure",
      "Escalate to IT if CBS stop payment module is unresponsive"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Stop Payment Not Processed",
    "investigation_steps": [
      "Retrieve stop payment request submission details from CBS",
      "Check maker-checker workflow status for stop payment instruction",
      "Verify if request was received within the bank's stop payment acceptance window",
      "Review CTS clearing queue to check if cheque is already in process"
    ],
    "next_best_actions": [
      "Process stop payment in CBS immediately through maker-checker approval",
      "Flag cheque in CTS clearing queue to prevent payment if still in process",
      "Escalate urgently if cheque is at risk of being presented imminently"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Stop Payment Charges Incorrect",
    "investigation_steps": [
      "Retrieve stop payment charge deduction details from CBS",
      "Verify applicable stop payment charge as per approved fee schedule",
      "Check if charge was applied correctly for the account type and request type"
    ],
    "next_best_actions": [
      "Reverse incorrect stop payment charge in CBS",
      "Apply correct charge as per approved fee schedule",
      "Update charge parameters in CBS if configuration error identified"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Cleared After Stop Payment",
    "investigation_steps": [
      "Retrieve stop payment instruction record and active status from CBS at time of clearing",
      "Check CTS clearing system logs for stop payment validation during presentation",
      "Verify if stop payment was registered for the correct cheque number and account",
      "Review CTS integration with CBS stop payment module"
    ],
    "next_best_actions": [
      "Initiate payment reversal and recover funds from beneficiary account",
      "Credit drawee account for the erroneously cleared amount",
      "Escalate to IT to investigate and fix CTS-CBS stop payment validation failure",
      "Reimburse any consequential charges incurred by customer due to bank error"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Stop Payment Confirmation Not Received",
    "investigation_steps": [
      "Verify stop payment registration status in CBS",
      "Check if confirmation was dispatched via SMS, email, or physical letter",
      "Review communication dispatch log for stop payment confirmation",
      "Verify registered mobile number and email ID in CBS"
    ],
    "next_best_actions": [
      "Re-dispatch stop payment confirmation via registered email or SMS",
      "Generate and share written confirmation from CBS stop payment record",
      "Update contact details in CBS if dispatch failed due to incorrect details"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Stop Payment Cancellation Failed",
    "investigation_steps": [
      "Retrieve stop payment cancellation request from CBS",
      "Check CBS error code at time of cancellation failure",
      "Verify if cancellation request was made for a valid and active stop payment instruction",
      "Review maker-checker workflow status for stop payment cancellation"
    ],
    "next_best_actions": [
      "Re-raise stop payment cancellation in CBS after resolving error",
      "Complete maker-checker approval for cancellation",
      "Escalate to IT if CBS stop payment cancellation module is non-functional"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Block Request Failed",
    "investigation_steps": [
      "Retrieve cheque block request log from CBS",
      "Check CBS error code returned at time of block request failure",
      "Verify if cheque series or leaf numbers are valid in CBS records",
      "Check if account is eligible for cheque block request"
    ],
    "next_best_actions": [
      "Re-raise cheque block request in CBS after resolving error",
      "Correct cheque series or leaf number details if data entry error caused failure",
      "Escalate to IT if CBS cheque block module is unresponsive"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Series Block Not Updated",
    "investigation_steps": [
      "Retrieve cheque series block request and processing status from CBS",
      "Verify if block was registered in CBS cheque management module",
      "Check maker-checker approval status for cheque series block"
    ],
    "next_best_actions": [
      "Update cheque series block in CBS after maker-checker approval",
      "Verify block is reflected in CTS clearing system to prevent payment",
      "Escalate to IT if CBS cheque management module is not updating"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Stop Payment Request Pending",
    "investigation_steps": [
      "Retrieve stop payment request and pending status from CBS",
      "Check maker-checker workflow stage for stop payment instruction",
      "Verify if CTS clearing deadline is approaching for the cheque"
    ],
    "next_best_actions": [
      "Immediately complete maker-checker approval for stop payment",
      "Flag cheque in CTS clearing queue if presentation is imminent",
      "Escalate urgently to branch operations for immediate processing"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Stop Payment Applied to Wrong Cheque",
    "investigation_steps": [
      "Retrieve stop payment record and verify cheque number and account in CBS",
      "Compare stop payment details with customer's original request",
      "Check if data entry error caused wrong cheque number to be stopped",
      "Verify impact on wrongly stopped cheque (presented or pending)"
    ],
    "next_best_actions": [
      "Remove stop payment from incorrectly stopped cheque in CBS",
      "Register stop payment on correct cheque number",
      "Reverse cheque return if wrongly stopped cheque was already returned",
      "Reimburse cheque return charges caused by incorrect stop payment"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Bounce Charges Incorrect",
    "investigation_steps": [
      "Retrieve cheque bounce charge details and charge code from CBS",
      "Verify applicable bounce charge as per fee schedule for the account type",
      "Check if charge was applied for both outward and inward return correctly",
      "Review RBI and internal guidelines on cheque return charge applicability"
    ],
    "next_best_actions": [
      "Reverse incorrect bounce charge in CBS",
      "Apply correct cheque bounce charge per approved fee schedule",
      "Update charge parameters in CBS if configuration error identified"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Return Charges Incorrect",
    "investigation_steps": [
      "Retrieve cheque return charge transaction from CBS",
      "Verify applicable return charge for the return reason code applied",
      "Check if charge differentiation between inward and outward return is correct",
      "Verify approved fee schedule for cheque return charges"
    ],
    "next_best_actions": [
      "Reverse incorrect cheque return charge in CBS",
      "Apply correct return charge as per approved schedule",
      "Update charge configuration in CBS if error identified"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Wrong Penalty Charged",
    "investigation_steps": [
      "Retrieve penalty charge transaction details from CBS",
      "Verify applicable penalty and its basis (return reason, frequency, amount)",
      "Check if penalty was applied as per internal or regulatory guidelines",
      "Compare applied penalty with approved penalty schedule"
    ],
    "next_best_actions": [
      "Reverse incorrect penalty in CBS",
      "Apply correct penalty as per approved schedule",
      "Update penalty configuration in CBS if parameter error identified"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Returned Due to Bank Error",
    "investigation_steps": [
      "Retrieve cheque return record and return reason code from CTS",
      "Verify drawee account balance and status at time of presentation",
      "Identify if return was due to MICR error, system error, or processing mistake",
      "Review branch or clearing operations processing logs"
    ],
    "next_best_actions": [
      "Re-present cheque immediately after correcting the error",
      "Reverse cheque return charges applied due to bank error",
      "Compensate for consequential loss caused by erroneous return if applicable",
      "Update CBS and CTS records with corrective action"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Returned Despite Sufficient Balance",
    "investigation_steps": [
      "Verify drawee account balance from CBS at exact time of cheque presentation",
      "Check if lien, hold, or earmark incorrectly reduced available balance",
      "Review CTS balance validation check at time of clearing",
      "Check if account had debit block at time of presentation"
    ],
    "next_best_actions": [
      "Re-present cheque after removing erroneous lien or block",
      "Reverse cheque return charges due to bank error",
      "Credit drawee account for any charges applied incorrectly",
      "Escalate to IT if balance validation in CTS is incorrect"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Dishonoured Incorrectly",
    "investigation_steps": [
      "Retrieve dishonour record and return reason code from CBS and CTS",
      "Verify drawee account status and balance at time of presentation",
      "Check if dishonour was due to system error, MICR mismatch, or incorrect stop payment",
      "Review manual authorization logs for the cheque"
    ],
    "next_best_actions": [
      "Re-present cheque after correcting root cause of erroneous dishonour",
      "Reverse dishonour charges and any consequential charges",
      "Update CBS and CTS records to correct dishonour status"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Return Memo Not Received",
    "investigation_steps": [
      "Verify cheque return record and return memo generation in CBS",
      "Check dispatch log for return memo delivery to customer",
      "Verify registered address, email, or mobile for memo dispatch",
      "Check if return memo was held at branch"
    ],
    "next_best_actions": [
      "Re-dispatch cheque return memo via registered email or post",
      "Issue copy of return memo from CBS records",
      "Update contact details in CBS if dispatch failed due to incorrect details"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Return Reason Incorrect",
    "investigation_steps": [
      "Retrieve return reason code applied from CBS and CTS records",
      "Verify actual reason for return against applied return code",
      "Check if return reason was auto-assigned by system or manually applied",
      "Review RBI/NPCI CTS return reason code list for correct code"
    ],
    "next_best_actions": [
      "Update CBS and CTS with correct return reason code",
      "Re-issue corrected return memo with accurate reason to customer",
      "Escalate to CTS operations team if system is assigning incorrect return codes"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Wrong Insufficient Funds Status",
    "investigation_steps": [
      "Verify actual balance in CBS at time of cheque presentation",
      "Check if insufficient funds flag was triggered by lien, hold, or incorrect available balance",
      "Review CTS balance check logs for the transaction",
      "Confirm whether return reason 'insufficient funds' was correctly applied"
    ],
    "next_best_actions": [
      "Remove erroneous lien or hold from CBS",
      "Re-present cheque if balance was sufficient and return was in error",
      "Correct return reason in CBS and CTS records",
      "Reverse bounce charges if return was due to bank error"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Bounce Record Incorrect",
    "investigation_steps": [
      "Retrieve cheque bounce record from CBS",
      "Verify if bounce was genuine or resulted from bank processing error",
      "Check CTS clearing records against CBS bounce entry",
      "Review customer's transaction history for the date of alleged bounce"
    ],
    "next_best_actions": [
      "Correct or delete erroneous bounce record in CBS",
      "Issue a corrected statement or certificate reflecting accurate bounce record",
      "Escalate to compliance if incorrect bounce record affects customer's credit profile"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Issuance Delay",
    "investigation_steps": [
      "Retrieve demand draft issuance request from CBS",
      "Check CBS printing and dispatch queue for the DD",
      "Verify if debit from customer account was processed",
      "Review branch DD issuance processing logs"
    ],
    "next_best_actions": [
      "Expedite DD issuance at branch or central processing",
      "Ensure customer account debit is reflected in CBS",
      "Dispatch DD to customer or beneficiary on priority"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Not Issued",
    "investigation_steps": [
      "Verify if DD issuance request was registered in CBS",
      "Check if customer account was debited for DD amount and charges",
      "Review CBS DD module for processing errors",
      "Check branch DD register for the request"
    ],
    "next_best_actions": [
      "Issue DD in CBS and debit customer account if not yet processed",
      "Refund DD charges if debited but DD not issued",
      "Process DD on priority and dispatch to customer"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Lost",
    "investigation_steps": [
      "Retrieve DD details (number, amount, payee, drawee branch) from CBS",
      "Verify if DD was lost before or after dispatch to customer",
      "Check courier dispatch and tracking records",
      "Verify if DD has been presented for payment"
    ],
    "next_best_actions": [
      "Place stop payment on lost DD in CBS",
      "Issue duplicate DD after customer submits indemnity bond",
      "Coordinate with drawee branch to flag original DD as lost",
      "Update CBS with stop payment and duplicate issuance details"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Cancellation Delay",
    "investigation_steps": [
      "Retrieve DD cancellation request from CBS",
      "Verify if DD is in the bank's possession and unpaid",
      "Check maker-checker workflow status for cancellation",
      "Review branch processing queue for DD cancellation requests"
    ],
    "next_best_actions": [
      "Process DD cancellation in CBS after maker-checker approval",
      "Refund DD amount to customer account after cancellation",
      "Deduct applicable cancellation charges per fee schedule"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Refund Pending",
    "investigation_steps": [
      "Retrieve DD cancellation record and refund status from CBS",
      "Verify if DD cancellation was completed in CBS",
      "Check if refund credit to customer account was processed",
      "Review GL entries for DD cancellation and refund"
    ],
    "next_best_actions": [
      "Process refund credit to customer account in CBS",
      "Reconcile DD GL account and post refund entry",
      "Update CBS with refund details and completion status"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Amount Incorrect",
    "investigation_steps": [
      "Retrieve DD issuance record and compare amount with customer's request",
      "Check CBS DD printing data for amount entered",
      "Verify if data entry error or system error caused incorrect amount",
      "Check if incorrect DD has been presented or encashed"
    ],
    "next_best_actions": [
      "Cancel incorrect DD and issue fresh DD for correct amount",
      "Adjust customer account debit for correct DD amount",
      "Place stop payment on incorrect DD if already dispatched"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Duplicate Issued",
    "investigation_steps": [
      "Retrieve all DD issuance records for the same request in CBS",
      "Verify if duplicate was issued due to system error or manual processing error",
      "Check if both DDs have been dispatched or encashed",
      "Review CBS DD GL account for double debit"
    ],
    "next_best_actions": [
      "Place stop payment on duplicate DD immediately",
      "Refund duplicate debit to customer account",
      "Recover duplicate DD if still unencashed",
      "Update CBS records to cancel duplicate DD"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Encashment Failed",
    "investigation_steps": [
      "Retrieve DD details and drawee branch records",
      "Check if DD is valid, unpaid, and within validity period",
      "Verify drawee branch CBS connectivity and processing status",
      "Check for stop payment or hold on the DD in CBS"
    ],
    "next_best_actions": [
      "Remove erroneous stop payment or hold if DD is valid",
      "Coordinate with drawee branch to process encashment",
      "Escalate to drawee branch manager if encashment is being incorrectly refused"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Expired",
    "investigation_steps": [
      "Retrieve DD validity period from CBS (typically 3 months from date of issue)",
      "Verify DD date and current date to confirm expiry",
      "Check if DD was presented within validity period",
      "Review bank's policy on DD revalidation"
    ],
    "next_best_actions": [
      "Process DD revalidation at issuing branch upon customer request",
      "Issue fresh DD after cancelling expired instrument",
      "Update CBS with revalidated DD details"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Demand Draft Status Not Updated",
    "investigation_steps": [
      "Retrieve DD record from CBS and verify current status",
      "Check if DD encashment or cancellation has been processed but status not updated",
      "Review CBS DD module for status update lag",
      "Check drawee branch acknowledgement for DD payment"
    ],
    "next_best_actions": [
      "Manually update DD status in CBS",
      "Reconcile DD GL account with actual payment or cancellation records",
      "Escalate to IT if CBS DD status update is systematically delayed"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Pay Order Not Issued",
    "investigation_steps": [
      "Verify if pay order issuance request was registered in CBS",
      "Check if customer account was debited for pay order amount and charges",
      "Review CBS pay order module for processing errors",
      "Check branch pay order register"
    ],
    "next_best_actions": [
      "Issue pay order in CBS after debiting customer account",
      "Refund any charges debited if pay order was not issued",
      "Dispatch pay order to customer on priority"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Pay Order Cancellation Failed",
    "investigation_steps": [
      "Retrieve pay order cancellation request from CBS",
      "Verify if pay order is in the bank's possession and unpaid",
      "Check CBS error code at time of cancellation failure",
      "Review maker-checker workflow status for cancellation"
    ],
    "next_best_actions": [
      "Re-raise cancellation request in CBS after resolving error",
      "Complete maker-checker approval for cancellation",
      "Refund pay order amount to customer account after successful cancellation"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Banker's Cheque Delay",
    "investigation_steps": [
      "Retrieve banker's cheque issuance request and processing status from CBS",
      "Check branch printing and dispatch queue for the instrument",
      "Verify if debit from customer account was processed in CBS",
      "Review branch banker's cheque register"
    ],
    "next_best_actions": [
      "Expedite banker's cheque issuance at branch",
      "Confirm customer account debit in CBS",
      "Dispatch banker's cheque to customer on priority"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Banker's Cheque Not Delivered",
    "investigation_steps": [
      "Verify dispatch status and courier tracking for the banker's cheque",
      "Confirm registered address used for delivery in CBS",
      "Check if instrument was returned undelivered to bank"
    ],
    "next_best_actions": [
      "Initiate re-delivery to correct address",
      "Place stop payment on undelivered instrument if customer reports non-receipt",
      "Issue replacement banker's cheque after indemnity if original is confirmed undelivered"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Banker's Cheque Lost",
    "investigation_steps": [
      "Retrieve banker's cheque details from CBS",
      "Verify if lost before or after dispatch to customer",
      "Check if instrument has been presented for payment",
      "Review courier tracking if lost in transit"
    ],
    "next_best_actions": [
      "Place stop payment on lost banker's cheque in CBS",
      "Issue duplicate banker's cheque after receiving indemnity bond from customer",
      "Coordinate with drawee branch to flag original as lost",
      "Update CBS with stop payment and duplicate issuance details"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Certified Cheque Request Failed",
    "investigation_steps": [
      "Retrieve certified cheque request log from CBS",
      "Check CBS error code at time of request failure",
      "Verify account eligibility and balance sufficiency for certification",
      "Review branch processing log for the request"
    ],
    "next_best_actions": [
      "Re-raise certified cheque request in CBS after resolving failure reason",
      "Ensure sufficient balance is available for certification and charges",
      "Escalate to IT if CBS certified cheque module is non-functional"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Manager's Cheque Delay",
    "investigation_steps": [
      "Retrieve manager's cheque issuance request status from CBS",
      "Check branch issuance queue and printing status",
      "Verify if debit from customer account was completed",
      "Review authorization status from branch manager or authorized officer"
    ],
    "next_best_actions": [
      "Complete authorization and issue manager's cheque on priority",
      "Ensure customer account debit is processed in CBS",
      "Dispatch instrument to customer or beneficiary"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cashier's Order Not Issued",
    "investigation_steps": [
      "Verify if cashier's order request was registered in CBS",
      "Check if customer account was debited for the order amount and charges",
      "Review CBS cashier's order module for processing errors",
      "Check branch instrument register"
    ],
    "next_best_actions": [
      "Issue cashier's order in CBS and debit customer account",
      "Refund charges if debited but instrument not issued",
      "Dispatch instrument to customer on priority"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Instrument Verification Failed",
    "investigation_steps": [
      "Retrieve instrument details and verification failure reason from CBS",
      "Verify instrument number, payee name, amount, and signature against CBS records",
      "Check if verification failure was due to system error or genuine instrument defect",
      "Review MICR code accuracy on the instrument"
    ],
    "next_best_actions": [
      "Conduct manual verification by authorized officer",
      "Correct data entry error in CBS and retry verification",
      "Honour instrument after manual verification if found valid",
      "Return instrument with correct reason if genuinely defective"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Instrument Cancellation Pending",
    "investigation_steps": [
      "Retrieve instrument cancellation request and pending status from CBS",
      "Check maker-checker workflow status for cancellation",
      "Verify if instrument is still unpaid and in bank's possession",
      "Review branch processing queue for pending cancellation requests"
    ],
    "next_best_actions": [
      "Complete maker-checker approval and process cancellation in CBS",
      "Refund instrument amount to customer account post cancellation",
      "Deduct applicable cancellation charges per fee schedule"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Status Not Updated",
    "investigation_steps": [
      "Retrieve cheque record from CBS and verify current status",
      "Check CTS clearing system for latest cheque processing status",
      "Review CBS-CTS integration for status update feed",
      "Check if status update is pending due to batch processing lag"
    ],
    "next_best_actions": [
      "Manually update cheque status in CBS",
      "Trigger status refresh from CTS clearing system",
      "Escalate to IT if CBS-CTS status integration is failing systematically"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Tracking Not Available",
    "investigation_steps": [
      "Check CTS clearing system for cheque tracking data",
      "Verify if cheque reference number is correctly captured in CBS",
      "Review internet or mobile banking cheque tracking module availability",
      "Check if tracking data feed from CTS to digital channels is active"
    ],
    "next_best_actions": [
      "Retrieve cheque status from CBS/CTS and manually communicate to operations team",
      "Escalate to IT to restore cheque tracking feed to digital channels",
      "Provide cheque status from CBS as interim"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Enquiry Not Responding",
    "investigation_steps": [
      "Check CBS cheque enquiry module availability and uptime",
      "Verify internet or mobile banking cheque enquiry API response logs",
      "Review server error logs for cheque enquiry endpoint",
      "Check CTS system availability"
    ],
    "next_best_actions": [
      "Escalate to IT to restore CBS cheque enquiry module",
      "Provide cheque status manually from CBS records as interim",
      "Fix API or middleware issue causing enquiry failure"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque History Missing",
    "investigation_steps": [
      "Retrieve full cheque transaction history from CBS for the account",
      "Check if cheque history data is missing in CBS or only in digital channel display",
      "Verify CBS-to-digital channel data feed for cheque history",
      "Check if transactions were archived or purged from display"
    ],
    "next_best_actions": [
      "Retrieve cheque history from CBS archive and restore to display",
      "Fix digital channel data feed for cheque history",
      "Provide cheque history from CBS directly as interim"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Transaction Missing",
    "investigation_steps": [
      "Retrieve all cheque transactions from CBS for the account and period",
      "Verify if transaction is present in CBS but missing in statement or digital display",
      "Check CTS clearing records for the specific cheque",
      "Review reconciliation records for the clearing date"
    ],
    "next_best_actions": [
      "Post missing cheque transaction in CBS after reconciliation confirmation",
      "Fix data display issue in digital channel if transaction is present in CBS",
      "Escalate to reconciliation team if transaction is absent from both CBS and CTS"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Number Mismatch",
    "investigation_steps": [
      "Retrieve cheque issuance record from CBS and compare with physical cheque number",
      "Check MICR code on cheque for encoded cheque number accuracy",
      "Verify if cheque number mismatch is in CBS records or on physical instrument",
      "Review stationery printing data for the cheque book"
    ],
    "next_best_actions": [
      "Correct cheque number in CBS if data entry error caused mismatch",
      "Hot-list mismatched cheque leaf if printing error is confirmed",
      "Issue replacement cheque book if stationery printing is found defective"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Leaf Already Used Error",
    "investigation_steps": [
      "Retrieve cheque leaf status from CBS cheque management module",
      "Verify transaction history for the cheque leaf number",
      "Check if 'already used' status is correctly flagged in CBS",
      "Review CTS clearing records for the specific cheque leaf"
    ],
    "next_best_actions": [
      "Correct erroneous 'already used' flag in CBS if no prior payment is confirmed",
      "Provide customer with correct cheque leaf status from CBS records",
      "Escalate to IT if CBS is incorrectly marking unused leaves as used"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Sequence Incorrect",
    "investigation_steps": [
      "Retrieve cheque book issuance record and allocated leaf series from CBS",
      "Compare physical cheque sequence with CBS records",
      "Check stationery printing data for cheque sequence",
      "Verify MICR encoded sequence on the cheque book"
    ],
    "next_best_actions": [
      "Correct cheque sequence mapping in CBS",
      "Hot-list incorrectly sequenced cheque book if stationery error is confirmed",
      "Issue fresh cheque book with correct sequence",
      "Escalate to stationery unit for quality review"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Register Not Updated",
    "investigation_steps": [
      "Retrieve cheque register from CBS for the account",
      "Verify if recent cheque book issuance or cancellation is reflected in register",
      "Check CBS cheque management module for update lag",
      "Review batch job for cheque register update"
    ],
    "next_best_actions": [
      "Manually update cheque register in CBS",
      "Trigger cheque register update batch job",
      "Escalate to IT if systematic register update failure is identified"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Issuance Record Incorrect",
    "investigation_steps": [
      "Retrieve cheque book issuance record from CBS",
      "Compare issuance record details (leaf count, series, date) with physical cheque book",
      "Check stationery dispatch records against CBS issuance entry",
      "Verify if error is in CBS data or in physical stationery"
    ],
    "next_best_actions": [
      "Correct cheque issuance record in CBS",
      "Hot-list incorrect series if stationery error is identified",
      "Re-issue cheque book with correct details and update CBS record"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Crossed Cheque Cleared Incorrectly",
    "investigation_steps": [
      "Retrieve CTS cheque image and verify crossing type (general or special)",
      "Check if crossed cheque was paid over the counter instead of through clearing",
      "Verify payment mode used against crossing instruction on the instrument",
      "Review teller or branch processing log for the payment"
    ],
    "next_best_actions": [
      "Initiate recovery of funds if crossing instruction was violated",
      "Escalate to branch manager and compliance team",
      "File internal inquiry against processing officer if violation is confirmed",
      "Update CBS and flag incident for audit review"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Bearer Cheque Payment Dispute",
    "investigation_steps": [
      "Retrieve CBS and teller records for bearer cheque payment",
      "Verify if payment was made to correct bearer and proper identification was collected",
      "Check teller log for identity verification conducted at payment",
      "Review CTS image for bearer cheque marking"
    ],
    "next_best_actions": [
      "Retrieve identity proof collected at time of payment from branch records",
      "Escalate to branch manager if identity verification was inadequate",
      "File internal inquiry if fraudulent encashment is suspected",
      "Coordinate with law enforcement if fraud is confirmed"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Order Cheque Wrongly Paid",
    "investigation_steps": [
      "Retrieve CBS and teller records for order cheque payment",
      "Verify if endorsement on order cheque was verified before payment",
      "Check if payment was made to named payee or to another party without proper endorsement",
      "Review CTS image for endorsement details"
    ],
    "next_best_actions": [
      "Initiate recovery from unauthorized payee if payment was wrongly made",
      "Escalate to branch manager and compliance team",
      "File internal inquiry against processing officer",
      "Coordinate with law enforcement if fraud is confirmed"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Altered Cheque Accepted",
    "investigation_steps": [
      "Retrieve CTS cheque image and examine for alterations (amount, date, payee name)",
      "Verify CBS payment record and compare instrument details with account records",
      "Check if alteration was detected during CTS verification or manual review",
      "Review authentication and authorization trail for the payment"
    ],
    "next_best_actions": [
      "Initiate recovery of funds paid on altered instrument",
      "Escalate to fraud management and compliance team",
      "File police complaint for cheque alteration",
      "Conduct forensic examination of physical instrument if available",
      "Coordinate with legal team for recovery proceedings"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Forged Cheque Cleared",
    "investigation_steps": [
      "Retrieve CTS cheque image and compare signature with CBS specimen signature",
      "Verify instrument authenticity including paper quality, MICR, and printing",
      "Check if CTS signature verification was performed before payment",
      "Review CBS drawee account records for payment authorization"
    ],
    "next_best_actions": [
      "Initiate recovery of funds paid on forged instrument",
      "Block drawee account for debits pending investigation",
      "File police complaint for cheque forgery",
      "Escalate to fraud management, compliance, and legal team",
      "Coordinate with law enforcement and NPCI for fraud reporting"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Unauthorized Cheque Encashment",
    "investigation_steps": [
      "Retrieve CBS and teller records for the encashment transaction",
      "Verify if encashment was authorized by account holder",
      "Check identity verification conducted at time of encashment",
      "Review CTS image and teller log for encashment details"
    ],
    "next_best_actions": [
      "Initiate recovery of funds from encashing party",
      "Escalate to fraud management and compliance team",
      "File police complaint if fraudulent encashment is confirmed",
      "Process provisional credit to customer account as per RBI fraud liability guidelines"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Fraudulent Cheque Transaction",
    "investigation_steps": [
      "Retrieve complete transaction record from CBS and CTS",
      "Examine CTS cheque image for signs of fraud (forgery, alteration, counterfeit)",
      "Review fraud detection system alerts for the account",
      "Verify drawer account status and transaction authorization chain"
    ],
    "next_best_actions": [
      "Escalate to fraud management team immediately",
      "Place account under enhanced monitoring and apply transaction restrictions",
      "File police complaint and report to RBI/NPCI as required",
      "Initiate fund recovery proceedings",
      "Process provisional credit as per RBI fraud liability circular"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Tampering Complaint",
    "investigation_steps": [
      "Retrieve CTS cheque image and physical instrument if available",
      "Examine instrument for signs of tampering (erasing, overwriting, chemical alteration)",
      "Conduct forensic document examination if required",
      "Review payment authorization records in CBS for the tampered instrument"
    ],
    "next_best_actions": [
      "Escalate to fraud management and legal team",
      "Initiate recovery of funds if tampered cheque was paid",
      "File police complaint for cheque tampering",
      "Preserve CTS image and physical instrument as evidence",
      "Report to RBI/NPCI as per fraud reporting guidelines"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "MICR Code Error",
    "investigation_steps": [
      "Retrieve cheque MICR band data from CTS scanning records",
      "Compare MICR encoded data (bank code, branch code, account number, cheque number) with CBS records",
      "Verify if MICR error is in stationery printing or in CTS MICR reader",
      "Check stationery printing records for MICR encoding accuracy"
    ],
    "next_best_actions": [
      "Correct MICR data manually in CTS clearing if reader error is confirmed",
      "Hot-list MICR-defective cheque book and issue replacement with correct MICR",
      "Escalate to stationery unit for MICR quality correction",
      "Recalibrate MICR reader if hardware error is identified"
    ]
  },
  {
    "major_issue": "Cheque Services",
    "sub_issue": "Cheque Complaint Resolution Delay",
    "investigation_steps": [
      "Retrieve complaint details and submission timestamp from CRM system",
      "Check current status and ownership of complaint in CRM",
      "Review escalation history and pending actions in complaint log",
      "Identify bottleneck in cheque complaint resolution workflow"
    ],
    "next_best_actions": [
      "Reassign complaint to appropriate team for immediate resolution",
      "Escalate to senior operations management if resolution is delayed beyond regulatory timeline",
      "Update CRM with resolution action and expected closure date",
      "Ensure compliance with RBI grievance redressal timelines"
    ]
  }
],









