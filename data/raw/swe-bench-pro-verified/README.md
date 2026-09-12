---
license: apache-2.0
configs:
  - config_name: default
    data_files:
    - split: test
      path: swebench_pro_verified.jsonl
---
# SWE-Bench Pro Verified: Anti-hacking & Task refinement

SWE-Bench Pro has emerged as a standard benchmark for evaluating software engineering agents on challenging
repository-level tasks. However, our analysis work show that its evaluation is undermined by two sources of
unreliability: reward hacking, enabled by leakage of gold solutions or hidden evaluation information, and
task quality issues, including misleading problem statements and improperly scoped tests. These issues can
inflate benchmark performance and obscure agents’ true coding ability. We present SWE-Bench Pro Verified,
a verified version of SWE-Bench Pro that addresses both problems. Our approach combines anti-hacking
safeguards that eliminate major leakage channels without disrupting normal agent functionality, with task
refinement that minimally corrects inconsistencies within flawed instances. Evaluations on SWE-Bench Pro
Verified reveal that some models perform substantially worse than previously reported, suggesting that existing
results on SWE-Bench Pro may overestimate real software engineering capability. SWE-Bench Pro Verified
offers a more trustworthy benchmark for assessing software engineering agents.

![benchmark result](./benchmark.png)

---

## Part I: Anti-hacking fixes(All tasks)

Using **[AgentCompass](https://github.com/open-compass/AgentCompass)** to analyze trajectories from multiple models on **SWE-Bench Pro**, we found that the evaluated models mainly exhibit the following hacking behaviors:

- Using `git log` to directly recover the **golden patch**
- Directly reading reference code from the sandbox filesystem
- Pulling the corresponding code repository directly through various means
- Exploiting the project name and commit SHA in `instance_id` as shortcuts to obtain the **golden patch**

Ultimately, by implementing both **local leakage mitigation** and **network leakage mitigation** in **AgentCompass**, we achieved a practical balance between **anti-hacking safeguards** and **normal evaluation-time interaction**. This effectively reduced hacking behaviors in the evaluated models, enabling a more faithful assessment of their true capabilities.

---

## Part II: Task(Instructions and Testcases) Refinement (102 Tasks)

Based on publicly reported issues and our item-by-item review and analysis, we found that the sample quality issues in SWE-Bench Pro are mainly concentrated in the following areas:

- **Misleading prompts**: Incorrect or ambiguous prompts can steer the model toward interactions that do not align with the test cases, ultimately causing failures during the verification stage.
- **Overly narrow tests**: In some samples, the conditions checked by the test cases are neither specified in the prompt nor reasonably inferable from the repository context, which also leads to verification failures in the end.
- **Overly broad tests**: In some samples, the test cases do not fully cover the requirements described in the task instructions, allowing incomplete solutions to incorrectly pass verification.
- **Other issues**: Miscellaneous problems, such as formatting issues in certain test cases, can also result in verification errors.

In the end, we used an LLM-based pipeline for initial sample filtering and patching, followed by expert manual review on a case-by-case basis, and corrected 102 samples with quality issues. The corrected samples are as follows:


- **Misleading prompts** (22 samples)
```text
instance_ansible__ansible-d2f80991180337e2be23d6883064a67dcbaeb662-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5
instance_ansible__ansible-e40889e7112ae00a21a2c74312b330e67a766cc0-v1055803c3a812189a1133297f7f5468579283f86
instance_element-hq__element-web-5dfde12c1c1c0b6e48f17e3405468593e39d9492-vnan
instance_element-hq__element-web-fe14847bb9bb07cab1b9c6c54335ff22ca5e516a-vnan
instance_flipt-io__flipt-65581fef4aa807540cb933753d085feb0d7e736f
instance_flipt-io__flipt-86906cbfc3a5d3629a583f98e6301142f5f14bdb-v6bea0cc3a6fc532d7da914314f2944fc1cd04dee
instance_future-architect__vuls-ca3f6b1dbf2cd24d1537bfda43e788443ce03a0c
instance_gravitational__teleport-0cb341c926713bdfcbb490c69659a9b101df99eb
instance_gravitational__teleport-96019ce0be7a2c8e36363f359eb7c943b41dde70
instance_gravitational__teleport-c1b1c6a1541c478d7777a48fca993cc8206c73b9
instance_internetarchive__openlibrary-e390c1212055dd84a262a798e53487e771d3fb64-v8717e18970bcdc4e0d2cea3b1527752b21e74866
instance_navidrome__navidrome-56303cde23a4122d2447cbb266f942601a78d7e4
instance_protonmail__webclients-01ea5214d11e0df8b7170d91bafd34f23cb0f2b1
instance_protonmail__webclients-b387b24147e4b5ec3b482b8719ea72bee001462a
instance_qutebrowser__qutebrowser-16de05407111ddd82fa12e54389d532362489da9-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d
instance_qutebrowser__qutebrowser-394bfaed6544c952c6b3463751abab3176ad4997-vafb3e8e01b31319c66c4e666b8a3b1d8ba55db24
instance_qutebrowser__qutebrowser-a84ecfb80a00f8ab7e341372560458e3f9cfffa2-v2ef375ac784985212b1805e1d0431dc8f1b3c171
instance_qutebrowser__qutebrowser-c580ebf0801e5a3ecabc54f327498bb753c6d5f2-v2ef375ac784985212b1805e1d0431dc8f1b3c171
instance_qutebrowser__qutebrowser-f91ace96223cac8161c16dd061907e138fe85111-v059c6fdc75567943479b23ebca7c07b5e9a7f34c
instance_qutebrowser__qutebrowser-fcfa069a06ade76d91bac38127f3235c13d78eb1-v5fc38aaf22415ab0b70567368332beee7955b367
instance_qutebrowser__qutebrowser-fec187c2cb53d769c2682b35ca77858a811414a8-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d
instance_tutao__tutanota-51818218c6ae33de00cbea3a4d30daac8c34142e-vc4e41fd0029957297843cb9dec4a25c7c756f029
```

- **Overly narrow tests** (75 samples)
```text
instance_NodeBB__NodeBB-4327a09d76f10a79109da9d91c22120428d3bdb9-vnan
instance_NodeBB__NodeBB-f9ce92df988db7c1ae55d9ef96d247d27478bc70-vf2cf3cbd463b7ad942381f1c6d077626485a1e9e
instance_ansible__ansible-1bd7dcf339dd8b6c50bc16670be2448a206f4fdb-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5
instance_ansible__ansible-40ade1f84b8bb10a63576b0ac320c13f57c87d34-v6382ea168a93d80a64aab1fbd8c4f02dc5ada5bf
instance_ansible__ansible-83909bfa22573777e3db5688773bda59721962ad-vba6da65a0f3baefda7a058ebbd0a8dcafb8512f5
instance_ansible__ansible-b5e0293645570f3f404ad1dbbe5f006956ada0df-v0f01c69f1e2528b935359cfe578530722bca2c59
instance_ansible__ansible-b6290e1d156af608bd79118d209a64a051c55001-v390e508d27db7a51eece36bb6d9698b63a5b638a
instance_ansible__ansible-bec27fb4c0a40c5f8bbcf26a475704227d65ee73-v30a923fb5c164d6cd18280c02422f75e611e8fb2
instance_ansible__ansible-d33bedc48fdd933b5abd65a77c081876298e2f07-v0f01c69f1e2528b935359cfe578530722bca2c59
instance_ansible__ansible-d72025be751c894673ba85caa063d835a0ad3a8c-v390e508d27db7a51eece36bb6d9698b63a5b638a
instance_ansible__ansible-ea04e0048dbb3b63f876aad7020e1de8eee9f362-v1055803c3a812189a1133297f7f5468579283f86
instance_ansible__ansible-eea46a0d1b99a6dadedbb6a3502d599235fa7ec3-v390e508d27db7a51eece36bb6d9698b63a5b638a
instance_element-hq__element-web-71fe08ea0f159ccb707904d87f0a4aef205a167c-vnan
instance_element-hq__element-web-75c2c1a572fa45d1ea1d1a96e9e36e303332ecaa-vnan
instance_element-hq__element-web-7c63d52500e145d6fff6de41dd717f61ab88d02f-vnan
instance_element-hq__element-web-aeabf3b18896ac1eb7ae9757e66ce886120f8309-vnan
instance_element-hq__element-web-aec454dd6feeb93000380523cbb0b3681c0275fd-vnan
instance_element-hq__element-web-b007ea81b2ccd001b00f332bee65070aa7fc00f9-vnan
instance_element-hq__element-web-cf3c899dd1f221aa1a1f4c5a80dffc05b9c21c85-vnan
instance_element-hq__element-web-e15ef9f3de36df7f318c083e485f44e1de8aad17
instance_flipt-io__flipt-02e21636c58e86c51119b63e0fb5ca7b813b07b1
instance_flipt-io__flipt-0fd09def402258834b9d6c0eaa6d3b4ab93b4446
instance_flipt-io__flipt-492cc0b158200089dceede3b1aba0ed28df3fb1d
instance_flipt-io__flipt-72d06db14d58692bfb4d07b1aa745a37b35956f3
instance_flipt-io__flipt-84806a178447e766380cc66b14dee9c6eeb534f4
instance_flipt-io__flipt-a42d38a1bb1df267c53d9d4a706cf34825ae3da9
instance_flipt-io__flipt-af7a0be46d15f0b63f16a868d13f3b48a838e7ce
instance_flipt-io__flipt-b2cd6a6dd73ca91b519015fd5924fde8d17f3f06
instance_flipt-io__flipt-b6cef5cdc0daff3ee99e5974ed60a1dc6b4b0d67
instance_flipt-io__flipt-c6a7b1fd933e763b1675281b30077e161fa115a1
instance_flipt-io__flipt-cd18e54a0371fa222304742c6312e9ac37ea86c1
instance_flipt-io__flipt-ea9a2663b176da329b3f574da2ce2a664fc5b4a1
instance_future-architect__vuls-030b2e03525d68d74cb749959aac2d7f3fc0effa
instance_future-architect__vuls-3c1489e588dacea455ccf4c352a3b1006902e2d4
instance_future-architect__vuls-4c04acbd9ea5b073efe999e33381fa9f399d6f27
instance_future-architect__vuls-6eff6a9329a65cc412e79b8f82444dfa3d0f0b5a
instance_future-architect__vuls-83bcca6e669ba2e4102f26c4a2b52f78c7861f1a
instance_future-architect__vuls-8d5ea98e50cf616847f4e5a2df300395d1f719e9
instance_future-architect__vuls-aaea15e516ece43978cf98e09e52080478b1d39f
instance_future-architect__vuls-d18e7a751d07260d75ce3ba0cd67c4a6aebfd967
instance_future-architect__vuls-e3c27e1817d68248043bd09d63cc31f3344a6f2c
instance_future-architect__vuls-fd18df1dd4e4360f8932bc4b894bd8b40d654e7c
instance_gravitational__teleport-3587cca7840f636489449113969a5066025dd5bf
instance_gravitational__teleport-46aa81b1ce96ebb4ebed2ae53fd78cd44a05da6c-vee9b09fb20c43af7e520f57e9239bbcf46b7113d
instance_gravitational__teleport-4e1c39639edf1ab494dd7562844c8b277b5cfa18-vee9b09fb20c43af7e520f57e9239bbcf46b7113d
instance_gravitational__teleport-4f771403dc4177dc26ee0370f7332f3fe54bee0f-vee9b09fb20c43af7e520f57e9239bbcf46b7113d
instance_gravitational__teleport-87a593518b6ce94624f6c28516ce38cc30cbea5a
instance_gravitational__teleport-bb562408da4adeae16e025be65e170959d1ec492-vee9b09fb20c43af7e520f57e9239bbcf46b7113d
instance_gravitational__teleport-dd3977957a67bedaf604ad6ca255ba8c7b6704e9
instance_internetarchive__openlibrary-3c48b4bb782189e0858e6c3fc7956046cf3e1cfb-v2d9a6c849c60ed19fd0858ce9e40b7cc8e097e59
instance_internetarchive__openlibrary-5fb312632097be7e9ac6ab657964af115224d15d-v0f5aece3601a5b4419f7ccec1dbda2071be28ee4
instance_internetarchive__openlibrary-798055d1a19b8fa0983153b709f460be97e33064-v13642507b4fc1f8d234172bf8129942da2c2ca26
instance_internetarchive__openlibrary-910b08570210509f3bcfebf35c093a48243fe754-v0f5aece3601a5b4419f7ccec1dbda2071be28ee4
instance_internetarchive__openlibrary-9bdfd29fac883e77dcbc4208cab28c06fd963ab2-v76304ecdb3a5954fcf13feb710e8c40fcf24b73c
instance_internetarchive__openlibrary-a48fd6ba9482c527602bc081491d9e8ae6e8226c-vfa6ff903cb27f336e17654595dd900fa943dcd91
instance_internetarchive__openlibrary-dbbd9d539c6d4fd45d5be9662aa19b6d664b5137-v08d8e8889ec945ab821fb156c04c7d2e2810debb
instance_internetarchive__openlibrary-e1e502986a3b003899a8347ac8a7ff7b08cbfc39-v08d8e8889ec945ab821fb156c04c7d2e2810debb
instance_navidrome__navidrome-3972616585e82305eaf26aa25697b3f5f3082288
instance_navidrome__navidrome-3982ba725883e71d4e3e618c61d5140eeb8d850a
instance_navidrome__navidrome-874b17b8f614056df0ef021b5d4f977341084185
instance_navidrome__navidrome-b3980532237e57ab15b2b93c49d5cd5b2d050013
instance_navidrome__navidrome-d0dceae0943b8df16e579c2d9437e11760a0626a
instance_navidrome__navidrome-dfa453cc4ab772928686838dc73d0130740f054e
instance_navidrome__navidrome-e12a14a87d392ac70ee4cc8079e3c3e0103dbcb2
instance_protonmail__webclients-281a6b3f190f323ec2c0630999354fafb84b2880
instance_protonmail__webclients-2f2f6c311c6128fe86976950d3c0c2db07b03921
instance_protonmail__webclients-369fd37de29c14c690cb3b1c09a949189734026f
instance_qutebrowser__qutebrowser-21b426b6a20ec1cc5ecad770730641750699757b-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d
instance_qutebrowser__qutebrowser-2e961080a85d660148937ee8f0f6b3445a8f2c01-v363c8a7e5ccdf6968fc7ab84a2053ac78036691d
instance_qutebrowser__qutebrowser-3d01c201b8aa54dd71d4f801b1dd12feb4c0a08a-v5fc38aaf22415ab0b70567368332beee7955b367
instance_qutebrowser__qutebrowser-70248f256f93ed9b1984494d0a1a919ddd774892-v2ef375ac784985212b1805e1d0431dc8f1b3c171
instance_qutebrowser__qutebrowser-7f9713b20f623fc40473b7167a082d6db0f0fd40-va0fd88aac89cde702ec1ba84877234da33adce8a
instance_qutebrowser__qutebrowser-85b867fe8d4378c8e371f055c70452f546055854-v2ef375ac784985212b1805e1d0431dc8f1b3c171
instance_qutebrowser__qutebrowser-a25e8a09873838ca9efefd36ea8a45170bbeb95c-vc2f56a753b62a190ddb23cd330c257b9cf560d12
instance_qutebrowser__qutebrowser-f631cd4422744160d9dcf7a0455da532ce973315-v35616345bb8052ea303186706cec663146f0f184
```

- **Overly borad tests** (3 samples)

```text
instance_NodeBB__NodeBB-04998908ba6721d64eba79ae3b65a351dcfbc5b5-vnan
instance_NodeBB__NodeBB-51d8f3b195bddb13a13ddc0de110722774d9bb1b-vf2cf3cbd463b7ad942381f1c6d077626485a1e9e
instance_flipt-io__flipt-9f8127f225a86245fa35dca4885c2daef824ee55
```

- **Other issues** (2 samples)
```text
instance_NodeBB__NodeBB-00c70ce7b0541cfc94afe567921d7668cdc8f4ac-vnan
instance_flipt-io__flipt-ebb3f84c74d61eee4d8c6875140b990eee62e146
```

---

## Contact

If you have any questions or suggestions, feel free to [open an issue on huggingface](https://huggingface.co/datasets/opencompass/SWEBench-Pro-Verified/discussions) or [open an issue on AgentCompass](https://github.com/open-compass/AgentCompass/issues).

---

## Acknowledgments

Special thanks to [ScaleAI/SWE-bench_Pro](https://huggingface.co/datasets/ScaleAI/SWE-bench_Pro), SWE-Bench Pro Verified is refined based on their original version. Also, thanks to all community users for reporting quality issues.

---

## Citation

If you use this dataset, please cite:

```bibtex
@misc{zheng2026swebenchproverifiedreliable,
      title={SWE-Bench Pro Verified: A Reliable Benchmark for Software Engineering Agents}, 
      author={Pujun Zheng and Zixin Shang and Shufan Jiang and Wenhui Tian and Dongsheng Zhu and Zerun Ma and Dingbo Yuan and Qi Zhang},
      year={2026},
      eprint={2609.08149},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2609.08149}, 
}

@misc{chen2026agentcompassunifiedevaluationinfrastructure,
      title={AgentCompass: A Unified Evaluation Infrastructure for Agent Capabilities}, 
      author={Kai Chen and Zichen Ding and Jiaye Ge and Shufan Jiang and Mo Li and Qingqiu Li and Zehao Li and Zonglin Li and Tianhao Liang and Shudong Liu and Zerun Ma and Zixin Shang and Wenhui Tian and Zun Wang and Liwei Wu and Zhenyu Wu and Jun Xu and Bowen Yang and Dingbo Yuan and Qi Zhang and Songyang Zhang and Peiheng Zhou and Dongsheng Zhu},
      year={2026},
      eprint={2607.13705},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2607.13705}, 
}
```