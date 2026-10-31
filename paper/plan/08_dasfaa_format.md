# Format và lịch DASFAA 2027

Đã đối chiếu CFP chính thức và template Springer trong ngày 30/10/2026. Nguồn: [Research Track CFP](https://dasfaa2027.github.io/CallforResearchTrack/list.htm), [Springer proceedings instructions](https://www.springer.com/gp/computer-science/lncs/conference-proceedings-guidelines).

| Hạng mục | Yêu cầu đã công bố |
|---|---|
| Ngôn ngữ | Tiếng Anh |
| Format | Springer LNCS |
| Độ dài | Tối đa 16 trang, **gồm references và appendices** |
| Abstract | Tối đa 200 từ |
| Review | Double blind |
| Tệp nộp | PDF |
| Originality | Chưa công bố; không concurrent submission |
| Deadline | 25/11/2026, 23:59 AoE |
| Giờ Việt Nam tương ứng | 26/11/2026, 18:59, UTC+7 |
| Notification | 25/01/2027 |
| Camera-ready | 20/02/2027 |
| Submission portal | [CMT DASFAA 2027](https://cmt3.research.microsoft.com/DASFAA2027/Submission/Index) |

Người được nhận cần tuân thủ registration/presentation theo CFP. Đối chiếu lại trang hội nghị trước khi nộp nếu có cập nhật. Không suy AI disclosure policy hoặc supplement policy khi CFP chưa nêu rõ.

## Template hiện hành

[ZIP LaTeX chính thức](https://cms-resources.apps.public.k8s.springernature.io/springer-cms/rest/v1/content/27851904/data/LaTeX2e%20Proceedings%20Template%20ZIP). Bản sample tải về ghi Version 2.25, 03/09/2026, dùng `llncs` với `runningheads`, T1 font encoding, `newtxtext` và `newtxmath`; bibliography style `splncs04`. Giữ class/layout chính thức; không tự giảm margin/font để vượt hạn mức.

Template Springer có gợi ý abstract chung dài hơn; yêu cầu riêng **≤200 từ của DASFAA** được ưu tiên. Table caption ở trên, figure caption ở dưới. Không cần dùng hết bốn heading levels; bản này nên chủ yếu có sections/subsections.

## Anonymization khi chuẩn bị nộp

PDF dùng Anonymous Authors, không affiliation/email, không acknowledgment nhận diện tác giả. Không chèn URL chứa username của kho riêng trong bản double blind; chuẩn bị anonymous artifact link nếu cần và nếu hội nghị cho phép. Tên tài liệu, PDF metadata, figure paths hiển thị và supplement cũng cần đồng nhất. Không xóa hoặc thay kho dữ liệu công khai như một phần của việc viết.

Trong manuscript chỉ giữ tên khoa học của dataset/model/method và tham số cần tái lập. Các file nguồn nội bộ, run labels, checksum, upload checklist và lịch sử debug không xuất hiện ở bảng/hình/nội dung paper.

Trước khi nộp: kiểm PDF thực tế không quá 16 trang; abstract đếm theo bản cuối; citations/references đầy đủ; font embed và hình đọc được; mọi con số đồng nhất với bảng đã chốt. Bản PDF đầu tiên để tác giả revise không tự đồng nghĩa bản sẵn sàng nộp.
