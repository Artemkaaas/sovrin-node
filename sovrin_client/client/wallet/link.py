from typing import List

from plenum.common.constants import NAME, NONCE
from plenum.common.signer_did import DidIdentity
from plenum.common.types import f
from plenum.common.util import prettyDateDifference, friendlyToRaw
from plenum.common.verifier import DidVerifier
from anoncreds.protocol.types import AvailableClaim

from sovrin_common.exceptions import InvalidLinkException, \
    RemoteEndpointNotFound, NotFound


class constant:
    TRUST_ANCHOR = "Trust Anchor"
    SIGNER_IDENTIFIER = "Identifier"
    SIGNER_VER_KEY = "Verification Key"
    SIGNER_VER_KEY_EMPTY = '<empty>'

    REMOTE_IDENTIFIER = "Remote"
    REMOTE_VER_KEY = "Remote Verification Key"
    REMOTE_VER_KEY_SAME_AS_ID = '<same as Remote>'
    REMOTE_END_POINT = "Remote endpoint"
    SIGNATURE = "Signature"
    CLAIM_REQUESTS = "Claim Requests"
    AVAILABLE_CLAIMS = "Available Claims"
    RECEIVED_CLAIMS = "Received Claims"

    LINK_NONCE = "Nonce"
    LINK_STATUS = "Invitation status"
    LINK_LAST_SYNCED = "Last Synced"
    LINK_LAST_SEQ_NO = "Last Sync no"
    LINK_STATUS_ACCEPTED = "Accepted"

    LINK_NOT_SYNCHRONIZED = "<this link has not yet been synchronized>"
    UNKNOWN_WAITING_FOR_SYNC = "<unknown, waiting for sync>"

    LINK_ITEM_PREFIX = '\n    '

    NOT_AVAILABLE = "Not Available"

    NOT_ASSIGNED = "not yet assigned"


class Link:
    def __init__(self,
                 name,
                 localIdentifier=None,
                 localVerkey=None,
                 trustAnchor=None,
                 remoteIdentifier=None,
                 remoteEndPoint=None,
                 remotePubkey=None,
                 invitationNonce=None,
                 proofRequests=None,
                 internalId=None,
                 remote_verkey=None):
        self.name = name
        self.localIdentifier = localIdentifier
        self.localVerkey = localVerkey
        self.trustAnchor = trustAnchor
        self.remoteIdentifier = remoteIdentifier
        self.remoteEndPoint = remoteEndPoint
        self.remotePubkey = remotePubkey
        self.invitationNonce = invitationNonce

        # for optionally storing a reference to an identifier in another system
        # for example, a college may already have a student ID for a particular
        # person, and that student ID can be put in this field
        self.internalId = internalId

        self.proofRequests = proofRequests or []  # type: List[ProofRequest]
        self.verifiedClaimProofs = []
        self.availableClaims = []  # type: List[AvailableClaim]

        self.remoteVerkey = remote_verkey
        self.linkStatus = None
        self.linkLastSynced = None
        self.linkLastSyncNo = None

    def __repr__(self):
        return self.key

    @property
    def key(self):
        return self.name

    @property
    def isRemoteEndpointAvailable(self):
        return self.remoteEndPoint and self.remoteEndPoint != \
                                       constant.NOT_AVAILABLE

    @property
    def isAccepted(self):
        return self.linkStatus == constant.LINK_STATUS_ACCEPTED

    def __str__(self):
        localIdr = self.localIdentifier if self.localIdentifier \
            else constant.NOT_ASSIGNED
        trustAnchor = self.trustAnchor or ""
        trustAnchorStatus = '(not yet written to Sovrin)'
        if self.remoteVerkey is not None:
            if self.remoteIdentifier == self.remoteVerkey:
                remoteVerKey = constant.REMOTE_VER_KEY_SAME_AS_ID
            else:
                remoteVerKey = self.remoteVerkey
        else:
            remoteVerKey = constant.UNKNOWN_WAITING_FOR_SYNC

        remoteEndPoint = self.remoteEndPoint or \
                         constant.UNKNOWN_WAITING_FOR_SYNC
        if isinstance(remoteEndPoint, tuple):
            remoteEndPoint = "{}:{}".format(*remoteEndPoint)
        linkStatus = 'not verified, remote verkey unknown'
        linkLastSynced = prettyDateDifference(self.linkLastSynced) or \
                         constant.LINK_NOT_SYNCHRONIZED

        if linkLastSynced != constant.LINK_NOT_SYNCHRONIZED and \
                        remoteEndPoint == constant.UNKNOWN_WAITING_FOR_SYNC:
            remoteEndPoint = constant.NOT_AVAILABLE

        if self.isAccepted:
            trustAnchorStatus = '(confirmed)'
            if self.remoteVerkey is None:
                remoteVerKey = constant.REMOTE_VER_KEY_SAME_AS_ID
            linkStatus = self.linkStatus

        # TODO: The verkey would be same as the local identifier until we
        # support key rotation
        # TODO: This should be set as verkey in case of DID but need it from
        # wallet
        verKey = self.localVerkey if self.localVerkey else constant.SIGNER_VER_KEY_EMPTY
        fixedLinkHeading = "Link"
        if not self.isAccepted:
            fixedLinkHeading += " (not yet accepted)"

        # TODO: Refactor to use string interpolation
        # try:
        fixedLinkItems = \
            '\n' \
            'Name: ' + self.name + '\n' \
            'Identifier: ' + localIdr + '\n' \
            'Trust anchor: ' + trustAnchor + ' ' + trustAnchorStatus + '\n' \
            'Verification key: ' + verKey + '\n' \
            'Signing key: <hidden>' '\n' \
            'Remote: ' + (self.remoteIdentifier or
                          constant.UNKNOWN_WAITING_FOR_SYNC) + '\n' \
            'Remote Verification key: ' + remoteVerKey + '\n' \
            'Remote endpoint: ' + remoteEndPoint + '\n' \
            'Invitation nonce: ' + self.invitationNonce + '\n' \
            'Invitation status: ' + linkStatus + '\n'

        optionalLinkItems = ""
        if len(self.proofRequests) > 0:
            optionalLinkItems += "Proof Request(s): {}". \
                                     format(", ".join([cr.name for cr in self.proofRequests])) \
                                 + '\n'

        if self.availableClaims:
            optionalLinkItems += self.avail_claims_str()

        if self.linkLastSyncNo:
            optionalLinkItems += 'Last sync seq no: ' + self.linkLastSyncNo \
                                 + '\n'

        fixedEndingLines = 'Last synced: ' + linkLastSynced

        linkItems = fixedLinkItems + optionalLinkItems + fixedEndingLines
        indentedLinkItems = constant.LINK_ITEM_PREFIX.join(
            linkItems.splitlines())
        return fixedLinkHeading + indentedLinkItems

    def avail_claims_str(self):
        claim_names = [name for name, _, _ in self.availableClaims]
        return "Available Claim(s): {}".\
                   format(", ".join(claim_names)) + '\n'

    @staticmethod
    def validate(invitationData):

        def checkIfFieldPresent(msg, searchInName, fieldName):
            if not msg.get(fieldName):
                raise InvalidLinkException(
                    "Field not found in {}: {}".format(searchInName, fieldName))

        checkIfFieldPresent(invitationData, 'given input', 'sig')
        checkIfFieldPresent(invitationData, 'given input', 'link-invitation')
        linkInvitation = invitationData.get("link-invitation")
        linkInvitationReqFields = [f.IDENTIFIER.nm, NAME, NONCE]
        for fn in linkInvitationReqFields:
            checkIfFieldPresent(linkInvitation, 'link-invitation', fn)

    def getRemoteEndpoint(self, required=False):
        if not self.remoteEndPoint and required:
            raise RemoteEndpointNotFound

        if isinstance(self.remoteEndPoint, tuple):
            return self.remoteEndPoint
        elif isinstance(self.remoteEndPoint, str):
            ip, port = self.remoteEndPoint.split(":")
            return ip, int(port)
        elif self.remoteEndPoint is None:
            return None
        else:
            raise ValueError('Cannot convert endpoint {} to HA'.
                             format(self.remoteEndPoint))

    @property
    def remoteVerkey(self):
        if not hasattr(self, '_remoteVerkey'):
            return None

        if self._remoteVerkey is None:
            return None

        # This property should be used to fetch verkey compared to
        # remoteVerkey, its a more consistent name and takes care of
        # abbreviated verkey
        i = DidIdentity(self.remoteIdentifier, verkey=self._remoteVerkey)

        return i.verkey

    @property
    def full_remote_verkey(self):
        verkey = self.remoteVerkey
        if verkey is None:
            return None

        i = DidIdentity(self.remoteIdentifier, verkey=verkey)
        full_verkey = i.full_verkey
        return full_verkey

    @remoteVerkey.setter
    def remoteVerkey(self, new_val):
        self._remoteVerkey = new_val

    def find_available_claims(self, name=None, version=None, origin=None):
        return [ac for ac in self.availableClaims
                if (not name or name == ac.name) and
                (not version or version == ac.version) and
                (not origin or origin == ac.origin)]

    def find_available_claim(self, name=None, version=None, origin=None,
                             max_one=True, required=True):
        _ = self.find_available_claims(name, version, origin)
        assert not max_one or len(_) <= 1, \
            'more than one matching available claim found'
        if required and len(_) == 0:
            raise NotFound
        return _[0] if _ else None

    def find_proof_requests(self, name=None, version=None):
        return [pr for pr in self.proofRequests
                if (not name or name == pr.name) and
                (not version or version == pr.version)]

    def find_proof_request(self, name=None, version=None,
                           max_one=True, required=True):
        _ = self.find_proof_requests(name, version)
        assert not max_one or len(_) <= 1, \
            'more than one matching available claim found'
        if required and len(_) == 0:
            raise NotFound
        return _[0] if _ else None
