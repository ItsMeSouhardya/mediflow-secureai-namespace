// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

/// @title MediFlowIntegrity
/// @notice Stores only opaque bytes32 references and cryptographic hashes.
///         No patient identifier, filename, medical content, or consent purpose
///         is accepted by this contract.
contract MediFlowIntegrity {
    address public immutable owner;

    struct RecordProof {
        bytes32 contentHash;
        uint64 registeredAt;
    }

    struct ConsentProof {
        bytes32 patientRef;
        bytes32 granteeRef;
        bytes32 scopeHash;
        bytes32 periodRef;
        bytes32 revocationHash;
        uint64 grantedAt;
        uint64 revokedAt;
        bool active;
    }

    struct AuditAnchor {
        bytes32 merkleRoot;
        uint64 anchoredAt;
    }

    mapping(bytes32 => RecordProof) private recordProofs;
    mapping(bytes32 => ConsentProof) private consentProofs;
    mapping(bytes32 => AuditAnchor) private auditAnchors;

    event RecordRegistered(bytes32 indexed recordRef, bytes32 indexed contentHash, uint64 registeredAt);
    event ConsentGranted(
        bytes32 indexed consentRef,
        bytes32 indexed patientRef,
        bytes32 indexed granteeRef,
        bytes32 scopeHash,
        bytes32 periodRef,
        uint64 grantedAt
    );
    event ConsentRevoked(bytes32 indexed consentRef, bytes32 indexed revocationHash, uint64 revokedAt);
    event AuditRootAnchored(bytes32 indexed periodRef, bytes32 indexed merkleRoot, uint64 anchoredAt);

    error NotOwner();
    error ZeroValue();
    error AlreadyRegistered();
    error UnknownConsent();
    error ConsentNotActive();

    constructor() {
        owner = msg.sender;
    }

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    function registerRecord(bytes32 recordRef, bytes32 contentHash) external onlyOwner {
        if (recordRef == bytes32(0) || contentHash == bytes32(0)) revert ZeroValue();
        if (recordProofs[recordRef].registeredAt != 0) revert AlreadyRegistered();
        uint64 timestamp = uint64(block.timestamp);
        recordProofs[recordRef] = RecordProof(contentHash, timestamp);
        emit RecordRegistered(recordRef, contentHash, timestamp);
    }

    function verifyRecord(bytes32 recordRef, bytes32 contentHash) external view returns (bool) {
        RecordProof memory proof = recordProofs[recordRef];
        return proof.registeredAt != 0 && proof.contentHash == contentHash;
    }

    function getRecordProof(bytes32 recordRef) external view returns (bytes32 contentHash, uint64 registeredAt) {
        RecordProof memory proof = recordProofs[recordRef];
        return (proof.contentHash, proof.registeredAt);
    }

    function grantConsent(
        bytes32 consentRef,
        bytes32 patientRef,
        bytes32 granteeRef,
        bytes32 scopeHash,
        bytes32 periodRef
    ) external onlyOwner {
        if (
            consentRef == bytes32(0) || patientRef == bytes32(0) || granteeRef == bytes32(0)
                || scopeHash == bytes32(0) || periodRef == bytes32(0)
        ) revert ZeroValue();
        if (consentProofs[consentRef].grantedAt != 0) revert AlreadyRegistered();
        uint64 timestamp = uint64(block.timestamp);
        consentProofs[consentRef] = ConsentProof(
            patientRef, granteeRef, scopeHash, periodRef, bytes32(0), timestamp, 0, true
        );
        emit ConsentGranted(consentRef, patientRef, granteeRef, scopeHash, periodRef, timestamp);
    }

    function revokeConsent(bytes32 consentRef, bytes32 revocationHash) external onlyOwner {
        if (consentRef == bytes32(0) || revocationHash == bytes32(0)) revert ZeroValue();
        ConsentProof storage proof = consentProofs[consentRef];
        if (proof.grantedAt == 0) revert UnknownConsent();
        if (!proof.active) revert ConsentNotActive();
        uint64 timestamp = uint64(block.timestamp);
        proof.active = false;
        proof.revocationHash = revocationHash;
        proof.revokedAt = timestamp;
        emit ConsentRevoked(consentRef, revocationHash, timestamp);
    }

    function getConsentProof(bytes32 consentRef) external view returns (ConsentProof memory) {
        return consentProofs[consentRef];
    }

    function anchorAuditRoot(bytes32 periodRef, bytes32 merkleRoot) external onlyOwner {
        if (periodRef == bytes32(0) || merkleRoot == bytes32(0)) revert ZeroValue();
        if (auditAnchors[periodRef].anchoredAt != 0) revert AlreadyRegistered();
        uint64 timestamp = uint64(block.timestamp);
        auditAnchors[periodRef] = AuditAnchor(merkleRoot, timestamp);
        emit AuditRootAnchored(periodRef, merkleRoot, timestamp);
    }

    function getAuditAnchor(bytes32 periodRef) external view returns (bytes32 merkleRoot, uint64 anchoredAt) {
        AuditAnchor memory anchor = auditAnchors[periodRef];
        return (anchor.merkleRoot, anchor.anchoredAt);
    }
}
